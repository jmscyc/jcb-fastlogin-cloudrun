import asyncio
import time
import uuid
from typing import List, Dict, Any, Callable
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError
import database
import notify

TARGET_URL = "https://ezweb.easycard.com.tw/Event01/JCBLoginServlet"
BASE_URL = "https://ezweb.easycard.com.tw/Event01/JCBMainServlet"

STEALTH_JS = """
// 模擬真實瀏覽器環境，隱藏自動化痕跡
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en-US', 'en'] });
"""

class JCBLoginEngine:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.current_session_id = ""
        self.browser: Browser = None
        self.playwright = None
        self.log_subscribers: List[Callable[[str], None]] = []

    def subscribe_logs(self, callback: Callable[[str], None]):
        self.log_subscribers.append(callback)

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        print(formatted)
        for sub in self.log_subscribers:
            try:
                sub(formatted)
            except Exception:
                pass

    def stop(self):
        self.log("收到使用者手動中止訊號，正在停止執行程序...")
        self.stop_requested = True
        self.is_running = False

    async def run_task(self, selected_cards: List[Dict[str, Any]], config: Dict[str, Any]):
        if self.is_running:
            self.log("已有搶登任務正在執行中！")
            return
        
        self.is_running = True
        self.stop_requested = False
        self.current_session_id = str(uuid.uuid4())[:8]
        database.set_current_session_id(self.current_session_id)
        
        headless = config.get("headless", False)
        retry_interval_ms = config.get("retry_interval_ms", 500)
        max_concurrent_workers = config.get("max_concurrent_workers", 2)
        max_duration_seconds = config.get("max_duration_seconds", 0) # 0 代表不限時間，或指定秒數安全退場
        
        self.log(f"=== 啟動 JCB 並行搶登錄任務 (Session: {self.current_session_id}) ===")
        self.log(f"目標卡片數量: {len(selected_cards)} 張，多卡並行上限: {max_concurrent_workers} 組分頁")
        self.log(f"模式: {'無頭模式 (背景)' if headless else '可視化視窗 (Headed)'}")
        if max_duration_seconds > 0:
            self.log(f"最大監控時間限制: {max_duration_seconds} 秒")
        
        start_time = time.time()
        
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars"
                ]
            )
            
            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 850},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            await context.add_init_script(STEALTH_JS)
            
            # 使用 Semaphore 控制多卡並行數量
            sem = asyncio.Semaphore(max_concurrent_workers)
            
            async def worker(card: Dict[str, Any], idx: int):
                async with sem:
                    if self.stop_requested:
                        return
                    self.log(f"🚀 開始處理卡片 [{idx+1}/{len(selected_cards)}]: {card['name']} (尾號 {card['credit_card_suffix']})")
                    await self._process_single_card(context, card, retry_interval_ms, start_time, max_duration_seconds)

            tasks = [worker(card, i) for i, card in enumerate(selected_cards)]
            await asyncio.gather(*tasks)
                    
        except Exception as e:
            self.log(f"執行過程發生異常: {str(e)}")
        finally:
            self.is_running = False
            self.log("=== 搶登錄任務全數執行完畢 / 結束 ===")
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass

    async def _process_single_card(self, context: BrowserContext, card: Dict[str, Any], retry_interval_ms: int, start_time: float, max_duration_seconds: int) -> bool:
        page = await context.new_page()
        card_id = card["id"]
        card_name = card["name"]
        
        try:
            is_open = False
            attempts = 0
            
            while not is_open and not self.stop_requested:
                # 檢查是否超過最大限制秒數
                if max_duration_seconds > 0 and (time.time() - start_time) > max_duration_seconds:
                    self.log(f"[{card_name}] 已達最大監控時間 ({max_duration_seconds} 秒)，正常退出探測迴圈。")
                    break
                    
                attempts += 1
                try:
                    self.log(f"[{card_name}] 第 {attempts} 次探測登錄網頁...")
                    response = await page.goto(TARGET_URL, timeout=8000, wait_until="domcontentloaded")
                    
                    if not response or response.status >= 500:
                        self.log(f"[{card_name}] 伺服器回傳狀態碼 {response.status if response else 'Timeout'} (壅塞中)，準備重試...")
                        await asyncio.sleep(retry_interval_ms / 1000.0)
                        continue
                    
                    content = await page.content()
                    
                    if "非開放登錄期間" in content:
                        self.log(f"[{card_name}] 目前顯示「非開放登錄期間」，間隔 {retry_interval_ms}ms 再次刷新...")
                        await asyncio.sleep(retry_interval_ms / 1000.0)
                        continue
                    
                    if "已額滿" in content:
                        self.log(f"[{card_name}] 本梯次登錄已顯示「已額滿」！")
                        database.record_login(card_id, "FULL", "本次登錄期間已額滿", self.current_session_id)
                        await notify.send_notification("JCB 搶登額滿提醒", f"卡片【{card_name}】登錄時系統已顯示額滿。")
                        await page.close()
                        return False
                    
                    is_open = True
                    self.log(f"[{card_name}] ★★★ 登錄網頁已開放！立即開始填寫卡片資料 ★★★")
                    break
                    
                except PlaywrightError as pe:
                    self.log(f"[{card_name}] 連線超時或異常 ({str(pe)[:40]})，立刻重新嘗試...")
                    await asyncio.sleep(retry_interval_ms / 1000.0)
                except Exception as e:
                    self.log(f"[{card_name}] 刷新錯誤: {str(e)[:50]}，重試中...")
                    await asyncio.sleep(retry_interval_ms / 1000.0)

            if self.stop_requested or not is_open:
                await page.close()
                return False

            return await self._fill_and_submit(page, card)

        except Exception as e:
            self.log(f"[{card_name}] 處理異常: {str(e)}")
            database.record_login(card_id, "FAILED", f"異常: {str(e)[:50]}", self.current_session_id)
            try:
                await page.close()
            except Exception:
                pass
            return False

    async def _fill_and_submit(self, page: Page, card: Dict[str, Any]) -> bool:
        card_id = card["id"]
        card_name = card["name"]
        prefix = card["credit_card_prefix"]
        suffix = card["credit_card_suffix"]
        easycard = card["easycard_number"]
        
        self.log(f"[{card_name}] 自動注入卡號資訊...")
        
        try:
            fill_script = f"""
            () => {{
                const c1 = document.querySelector('input[name*="Credit"][name*="1"], input[id*="Credit"][id*="1"], input[name*="txtCreditCard1"], input[name="txtCard1"]');
                const c2 = document.querySelector('input[name*="Credit"][name*="2"], input[id*="Credit"][id*="2"], input[name*="txtCreditCard2"], input[name="txtCard2"]');
                if (c1) {{ c1.value = "{prefix}"; c1.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
                if (c2) {{ c2.value = "{suffix}"; c2.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
                
                const e1 = document.querySelector('#txtEasyCard1, input[name="txtEasyCard1"]');
                const e2 = document.querySelector('#txtEasyCard2, input[name="txtEasyCard2"]');
                const e3 = document.querySelector('#txtEasyCard3, input[name="txtEasyCard3"]');
                const e4 = document.querySelector('#txtEasyCard4, input[name="txtEasyCard4"]');
                
                if (e1 && e2 && e3 && e4) {{
                    e1.value = "{easycard[0:4]}";
                    e2.value = "{easycard[4:8]}";
                    e3.value = "{easycard[8:12]}";
                    e4.value = "{easycard[12:16]}";
                    [e1, e2, e3, e4].forEach(el => {{
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
                    }});
                }} else {{
                    const fullEasy = document.querySelector('input[name*="EasyCard"], input[id*="EasyCard"]');
                    if (fullEasy) {{
                        fullEasy.value = "{easycard}";
                        fullEasy.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            }}
            """
            await page.evaluate(fill_script)
            self.log(f"[{card_name}] 卡號資訊已填入完畢！")
            
            # 發送通知提醒使用者（若需驗證碼）
            await notify.send_notification("JCB 網頁已開放！", f"卡片【{card_name}】已自動填寫卡號，請儘速在瀏覽器視窗中完成驗證送出！")
            
            self.log(f"[{card_name}] 等候送出與登錄結果中 (最多等候 180 秒)...")
            
            start_time = time.time()
            while time.time() - start_time < 180 and not self.stop_requested:
                await asyncio.sleep(1)
                content = await page.content()
                
                if "登錄成功" in content or "成功登錄" in content:
                    self.log(f"[{card_name}] ★★★ 恭喜！登錄成功！ ★★★")
                    database.record_login(card_id, "SUCCESS", "登錄成功", self.current_session_id)
                    await notify.send_notification("🎉 JCB 登錄成功！", f"太棒了！卡片【{card_name}】已成功完成本月搶登錄！")
                    await asyncio.sleep(2)
                    await page.close()
                    return True
                    
                if "本月份已登錄" in content or "已登錄" in content:
                    self.log(f"[{card_name}] 系統顯示：本月份已登錄過！")
                    database.record_login(card_id, "ALREADY_REGISTERED", "本月份已登錄過", self.current_session_id)
                    await asyncio.sleep(2)
                    await page.close()
                    return True
                    
                if "已額滿" in content or "登錄期間已額滿" in content:
                    self.log(f"[{card_name}] 很抱歉，本次登錄已額滿！")
                    database.record_login(card_id, "FULL", "本次登錄期間已額滿", self.current_session_id)
                    await notify.send_notification("JCB 搶登額滿提醒", f"卡片【{card_name}】搶登時系統已額滿。")
                    await page.close()
                    return False
                    
            if self.stop_requested:
                await page.close()
                return False
                
            self.log(f"[{card_name}] 等候超時 (超過 3 分鐘)")
            database.record_login(card_id, "FAILED", "等待驗證或送出超時", self.current_session_id)
            await page.close()
            return False
            
        except Exception as e:
            self.log(f"[{card_name}] 填寫與送出失敗: {str(e)}")
            database.record_login(card_id, "FAILED", f"表單錯誤: {str(e)[:40]}", self.current_session_id)
            return False

engine = JCBLoginEngine()
