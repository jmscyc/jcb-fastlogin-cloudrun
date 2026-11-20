import asyncio
import os
import time
import uuid
from typing import List, Dict, Any, Callable
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError
import database
import notify
import ntp_utils
import ocr_utils
from sleep_guard import sleep_guard

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
        if callback not in self.log_subscribers:
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
        sleep_guard.acquire()
        
        headless = config.get("headless", False)
        base_interval_ms = config.get("retry_interval_ms", 500)
        max_concurrent_workers = config.get("max_concurrent_workers", 2)
        auto_captcha = config.get("auto_captcha", True) # 功能 1: 驗證碼自動辨識開關
        enable_ntp = config.get("enable_ntp", True)       # 功能 2: NTP 國家級精密校時
        sprint_mode = config.get("sprint_mode", True)     # 功能 2: 變速衝刺模式
        max_duration_seconds = config.get("max_duration_seconds", 0)
        
        self.log(f"=== 啟動 JCB 並行搶登錄任務 (Session: {self.current_session_id}) ===")
        dry_run = config.get("dry_run", False)
        if dry_run:
            self.log("【🧪 演練模擬測試模式已啟動】本輪搶登將載入本機全真模擬 JCB 登錄頁面，不發送真實請求。")

        self.log(f"目標卡片數量: {len(selected_cards)} 張，多卡並行上限: {max_concurrent_workers} 組分頁")
        self.log(f"瀏覽器模式: {'無頭模式 (背景)' if headless else '可視化視窗 (Headed)'}")
        self.log(f"驗證碼自動 OCR 辨識: {'【已啟用 🤖】' if auto_captcha else '【已關閉 (人工輸入)】'}")
        
        # 功能 2: NTP 校時
        ntp_offset = 0.0
        if enable_ntp:
            self.log("正在連線國家時間伺服器 (time.stdtime.gov.tw) 進行精密校時...")
            try:
                ntp_offset = await asyncio.to_thread(ntp_utils.get_ntp_offset)
                self.log(f"✓ NTP 校時完成！本地時間偏差: {ntp_offset*1000:.1f} 毫秒")
            except Exception as e:
                self.log(f"NTP 校時跳過: {e}")

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
            
            sem = asyncio.Semaphore(max_concurrent_workers)
            
            async def worker(card: Dict[str, Any], idx: int):
                async with sem:
                    if self.stop_requested:
                        return
                    self.log(f"🚀 開始處理卡片 [{idx+1}/{len(selected_cards)}]: {card['name']} (尾號 {card['credit_card_suffix']})")
                    await self._process_single_card(context, card, base_interval_ms, start_time, max_duration_seconds, auto_captcha, sprint_mode, ntp_offset, dry_run)

            tasks = [worker(card, i) for i, card in enumerate(selected_cards)]
            await asyncio.gather(*tasks)
                    
        except Exception as e:
            self.log(f"執行過程發生異常: {str(e)}")
        finally:
            self.is_running = False
            sleep_guard.release()
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

    async def _process_single_card(self, context: BrowserContext, card: Dict[str, Any], base_interval_ms: int, start_time: float, max_duration_seconds: int, auto_captcha: bool, sprint_mode: bool, ntp_offset: float, dry_run: bool = False) -> bool:
        page = await context.new_page()
        card_id = card["id"]
        card_name = card["name"]
        
        try:
            if dry_run:
                self.log(f"[{card_name}] 🧪 [模擬測試] 載入本機模擬 JCB 登錄網頁...")
                mock_html = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset="utf-8"><title>JCB 悠遊卡登錄 (全真演練模擬環境)</title>
                <style>
                    body {{ font-family: sans-serif; padding: 40px; background: #f8fafc; color: #1e293b; }}
                    .box {{ max-width: 500px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                    input {{ width: 100%; padding: 8px; margin: 8px 0 16px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; font-size: 14px; }}
                    button {{ background: #2563eb; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 15px; width: 100%; }}
                </style>
                </head>
                <body>
                    <div class="box">
                        <h2>【模擬】JCB 自動加值登錄頁面</h2>
                        <label>信用卡前6碼:</label>
                        <input type="text" id="txtCreditCard1" name="txtCreditCard1">
                        <label>信用卡後4碼:</label>
                        <input type="text" id="txtCreditCard2" name="txtCreditCard2">
                        <label>悠遊卡 16 碼:</label>
                        <input type="text" id="txtEasyCard1" name="txtEasyCard1">
                        <input type="hidden" id="txtEasyCard2" name="txtEasyCard2">
                        <input type="hidden" id="txtEasyCard3" name="txtEasyCard3">
                        <input type="hidden" id="txtEasyCard4" name="txtEasyCard4">
                        <label>驗證碼 (模擬):</label>
                        <div style="display:flex; gap:10px; align-items:center;">
                            <input type="text" id="txtValidCode" name="txtValidCode" style="margin:0;">
                            <span id="imgCaptcha" style="background:#e2e8f0; padding:6px 12px; font-weight:bold; letter-spacing:3px;">7890</span>
                        </div>
                        <br>
                        <button type="submit" id="btnSubmit" onclick="document.body.innerHTML='<div class=\\'box\\' style=\\'text-align:center;\\'><h2>登錄成功！</h2><p>恭喜您完成 2026 年度 JCB 晶片悠遊卡自動加值 10% 現金回饋活動登錄！</p><p>登錄序號：MOCK-202611209999</p></div>'; return false;">確認送出登錄</button>
                    </div>
                </body>
                </html>
                """
                await page.set_content(mock_html)
                await asyncio.sleep(0.5)
                return await self._fill_and_submit(page, card, auto_captcha)

            is_open = False
            attempts = 0
            
            while not is_open and not self.stop_requested:
                if max_duration_seconds > 0 and (time.time() - start_time) > max_duration_seconds:
                    self.log(f"[{card_name}] 已達最大監控時間 ({max_duration_seconds} 秒)，正常退出探測迴圈。")
                    break
                    
                attempts += 1
                
                # 功能 2: 計算變速衝刺間隔
                current_interval = base_interval_ms
                if sprint_mode:
                    now_precise = time.time() + ntp_offset
                    calc_interval, stage_desc = ntp_utils.get_sprint_interval(now_precise)
                    current_interval = calc_interval
                    if attempts % 10 == 1 or current_interval <= 150:
                        self.log(f"[{card_name}] 階段模式: {stage_desc}")

                try:
                    self.log(f"[{card_name}] 第 {attempts} 次探測登錄網頁 (間隔 {current_interval}ms)...")
                    response = await page.goto(TARGET_URL, timeout=8000, wait_until="domcontentloaded")
                    
                    if not response or response.status >= 500:
                        self.log(f"[{card_name}] 伺服器回傳狀態碼 {response.status if response else 'Timeout'} (壅塞中)，準備重試...")
                        await asyncio.sleep(current_interval / 1000.0)
                        continue
                    
                    content = await page.content()
                    
                    if "非開放登錄期間" in content:
                        await asyncio.sleep(current_interval / 1000.0)
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
                    self.log(f"[{card_name}] 連線重試 ({str(pe)[:35]})...")
                    await asyncio.sleep(current_interval / 1000.0)
                except Exception as e:
                    self.log(f"[{card_name}] 刷新錯誤: {str(e)[:40]}，重試中...")
                    await asyncio.sleep(current_interval / 1000.0)

            if self.stop_requested or not is_open:
                await page.close()
                return False

            return await self._fill_and_submit(page, card, auto_captcha)

        except Exception as e:
            self.log(f"[{card_name}] 處理異常: {str(e)}")
            database.record_login(card_id, "FAILED", f"異常: {str(e)[:50]}", self.current_session_id)
            try:
                await page.close()
            except Exception:
                pass
            return False

    async def _fill_and_submit(self, page: Page, card: Dict[str, Any], auto_captcha: bool) -> bool:
        card_id = card["id"]
        card_name = card["name"]
        prefix = card["credit_card_prefix"]
        suffix = card["credit_card_suffix"]
        easycard = card["easycard_number"]
        
        last_dialog_msg = []
        async def handle_dialog(dialog):
            msg = dialog.message
            last_dialog_msg.append(msg)
            self.log(f"[{card_name}] 收到網頁彈窗對話框: {msg}")
            try:
                await dialog.accept()
            except Exception:
                pass
        
        page.on("dialog", handle_dialog)
        
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
            
            # 功能 1: 驗證碼自動辨識與填入 (使用者勾選啟用時)
            if auto_captcha:
                self.log(f"[{card_name}] 🤖 正在掃描並辨識圖形驗證碼...")
                captcha_code = await ocr_utils.recognize_captcha_from_page(page)
                if captcha_code:
                    self.log(f"[{card_name}] 🎯 驗證碼辨識成功: [{captcha_code}]，正在自動填入...")
                    fill_captcha_js = f"""
                    () => {{
                        const vInput = document.querySelector('input[name*="Valid"], input[name*="valid"], input[id*="Valid"], input[id*="valid"], input[name*="Code"], input[id*="Code"]');
                        if (vInput) {{
                            vInput.value = "{captcha_code}";
                            vInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            vInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                    """
                    await page.evaluate(fill_captcha_js)
                    self.log(f"[{card_name}] ✓ 驗證碼已自動注入！嘗試自動點擊送出按鈕...")
                    # 嘗試觸發送出
                    submit_js = """
                    () => {
                        const btn = document.querySelector('button[type="submit"], input[type="submit"], input[value*="登錄"], input[value*="送出"], button:has-text("登錄")');
                        if (btn) btn.click();
                    }
                    """
                    await page.evaluate(submit_js)
                else:
                    self.log(f"[{card_name}] 提示: 網頁可能無驗證碼或由使用者手動輸入")
            else:
                self.log(f"[{card_name}] 使用者設定為手動輸入驗證碼，請在視窗中輸入...")

            # 發送即時通報
            await notify.send_notification("JCB 網頁已開放！", f"卡片【{card_name}】已自動填寫卡號，請確認送出！")
            
            self.log(f"[{card_name}] 等候送出與登錄結果中 (最多等候 180 秒)...")
            
            start_time = time.time()
            screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            
            async def take_screenshot(tag: str) -> str:
                try:
                    filename = f"{self.current_session_id}_{card_id}_{tag}_{int(time.time())}.png"
                    filepath = os.path.join(screenshot_dir, filename)
                    await page.screenshot(path=filepath, full_page=True)
                    return f"/static/screenshots/{filename}"
                except Exception:
                    return ""

            while time.time() - start_time < 180 and not self.stop_requested:
                await asyncio.sleep(1)
                content = await page.content()
                combined_text = content + " " + " ".join(last_dialog_msg)
                
                if "登錄成功" in combined_text or "成功登錄" in combined_text:
                    self.log(f"[{card_name}] ★★★ 恭喜！登錄成功！ ★★★")
                    shot_path = await take_screenshot("SUCCESS")
                    database.record_login(card_id, "SUCCESS", "登錄成功", self.current_session_id, shot_path)
                    await notify.send_notification("🎉 JCB 登錄成功！", f"太棒了！卡片【{card_name}】已成功完成本月搶登錄！")
                    await asyncio.sleep(2)
                    await page.close()
                    return True
                    
                if "本月份已登錄" in combined_text or "已登錄" in combined_text:
                    self.log(f"[{card_name}] 系統顯示：本月份已登錄過！")
                    shot_path = await take_screenshot("ALREADY")
                    database.record_login(card_id, "ALREADY_REGISTERED", "本月份已登錄過", self.current_session_id, shot_path)
                    await asyncio.sleep(2)
                    await page.close()
                    return True
                    
                if "已額滿" in combined_text or "登錄期間已額滿" in combined_text:
                    self.log(f"[{card_name}] 很抱歉，本次登錄已額滿！")
                    shot_path = await take_screenshot("FULL")
                    database.record_login(card_id, "FULL", "本次登錄期間已額滿", self.current_session_id, shot_path)
                    await notify.send_notification("JCB 搶登額滿提醒", f"卡片【{card_name}】搶登時系統已額滿。")
                    await page.close()
                    return False
                    
            if self.stop_requested:
                await page.close()
                return False
                
            self.log(f"[{card_name}] 等候超時 (超過 3 分鐘)")
            shot_path = await take_screenshot("TIMEOUT")
            database.record_login(card_id, "FAILED", "等待驗證或送出超時", self.current_session_id, shot_path)
            await page.close()
            return False
            
        except Exception as e:
            self.log(f"[{card_name}] 填寫與送出失敗: {str(e)}")
            database.record_login(card_id, "FAILED", f"表單錯誤: {str(e)[:40]}", self.current_session_id)
            return False

engine = JCBLoginEngine()
