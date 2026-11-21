import asyncio
import os
import re
import sys
import time
import uuid
import socket
import struct
import platform
from typing import List, Dict, Any, Callable, Optional, Tuple
import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError
import database

# ==============================================================================
# 1. 系統常數與目標網址
# ==============================================================================
TARGET_URL = "https://ezweb.easycard.com.tw/Event01/JCBLoginServlet"
BASE_URL = "https://ezweb.easycard.com.tw/Event01/JCBMainServlet"

STEALTH_JS = """
// 模擬真實瀏覽器環境，隱藏自動化痕跡
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en-US', 'en'] });
"""

# ==============================================================================
# 2. Windows 防休眠鎖 (Sleep Guard)
# ==============================================================================
class SleepGuard:
    """
    Windows 系統防休眠鎖：
    在預約倒數與搶登期間，防止電腦因閒置進入睡眠或黑屏關閉螢幕。
    在 Linux / macOS 上自動安全跳過。
    """
    def __init__(self):
        self.is_active = False
        self.is_windows = platform.system() == "Windows"

    def acquire(self):
        if not self.is_windows:
            return
        try:
            import ctypes
            # ES_CONTINUOUS = 0x80000000 | ES_SYSTEM_REQUIRED = 0x00000001 | ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            self.is_active = True
        except Exception as e:
            print(f"[SleepGuard] 無法啟用防休眠鎖: {e}")

    def release(self):
        if not self.is_windows or not self.is_active:
            return
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            self.is_active = False
        except Exception as e:
            print(f"[SleepGuard] 無法釋放防休眠鎖: {e}")

sleep_guard = SleepGuard()

# ==============================================================================
# 3. 國家級標準 NTP 精準校時與變速衝刺間隔計算 (NTP Utils)
# ==============================================================================
NTP_SERVERS = [
    "time.stdtime.gov.tw",
    "clock.stdtime.gov.tw",
    "pool.ntp.org",
    "time.google.com"
]

def get_ntp_offset(timeout: float = 2.0) -> float:
    """
    透過 UDP 協定向標準 NTP 伺服器對時，計算本地時鐘與標準時間之毫秒偏差 (Offset)。
    正值代表本地時間比 NTP 慢，負值代表本地時間比 NTP 快。
    """
    NTP_DELTA = 2208988800 # 1900 到 1970 的秒數
    for server in NTP_SERVERS:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(timeout)
            data = b'\x1b' + 47 * b'\0'
            t1 = time.time()
            client.sendto(data, (server, 123))
            resp, _ = client.recvfrom(1024)
            t4 = time.time()
            client.close()
            
            if resp and len(resp) >= 48:
                unpacked = struct.unpack('!12I', resp[0:48])
                t3 = unpacked[10] + float(unpacked[11]) / (2**32) - NTP_DELTA
                offset = t3 - ((t1 + t4) / 2)
                return offset
        except Exception:
            continue
    return 0.0

def get_sprint_interval(now_timestamp: float) -> Tuple[int, str]:
    """
    以台北時間 (UTC+8) 為基準，精準計算距離 09:00:00 搶登時刻的間隔與變速衝刺模式。
    """
    taipei_time = time.gmtime(now_timestamp + 8 * 3600)
    seconds_since_midnight_taipei = taipei_time.tm_hour * 3600 + taipei_time.tm_min * 60 + taipei_time.tm_sec
    target_seconds = 9 * 3600 # 09:00:00
    diff = target_seconds - seconds_since_midnight_taipei
    
    if diff > 1800 or diff < -300:
        return 500, "常規模式 (500ms)"
    if -30 <= diff <= 0:
        return 120, "⚡ 極限毫秒衝刺中 (120ms)"
    elif 0 < diff <= 5:
        return 150, "🔥 倒數 5 秒極速衝刺預備 (150ms)"
    elif 5 < diff <= 30:
        return 400, "🚀 倒數 30 秒提速巡邏 (400ms)"
    else:
        return 2000, f"⏳ 離 09:00 開搶尚有 {int(diff)} 秒，低頻節能巡航 (2000ms)"

# ==============================================================================
# 4. 驗證碼離線解析器 (Captcha OCR)
# ==============================================================================
def solve_captcha_image_sync(image_bytes: bytes) -> str:
    """
    1. 優先嘗試載入 ddddocr 進行毫秒級離線推論
    2. 若環境未安裝 ddddocr，回傳空字串 (改由人工或備援機制處理)
    """
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        res = ocr.classification(image_bytes)
        clean = re.sub(r'[^a-zA-Z0-9]', '', str(res)).strip()
        return clean
    except Exception:
        pass
    return ""

async def recognize_captcha_from_page(page: Page) -> Optional[str]:
    """
    在 Playwright 頁面上尋找驗證碼圖片元素，擷取圖片並執行解析。
    """
    candidate_selectors = [
        "img[src*='validate']",
        "img[src*='Validate']",
        "img[src*='captcha']",
        "img[src*='Captcha']",
        "img[src*='code']",
        "img[id*='validate']",
        "img[id*='Validate']",
        "img[id*='captcha']",
        "img[id*='Captcha']",
        "#imgCode",
        "#picCode",
        "#captchaImg"
    ]
    for sel in candidate_selectors:
        try:
            elem = await page.query_selector(sel)
            if elem and await elem.is_visible():
                img_bytes = await elem.screenshot()
                if img_bytes:
                    code = solve_captcha_image_sync(img_bytes)
                    if code and len(code) >= 3:
                        return code
        except Exception:
            continue
    return None

# 官方雙門戶網址 (登錄入口與活動首頁)
LOGIN_URL = TARGET_URL
MAIN_URL = "https://ezweb.easycard.com.tw/Event01/JCBMainServlet"

# ==============================================================================
# 5. 輕量化極速雙門戶 HTTP 探測器 (Dual Portal HTTP Probe + Proxy Support)
# ==============================================================================
async def fast_http_check(session: aiohttp.ClientSession, proxy_url: str = "") -> Tuple[bool, str]:
    """
    輕量化極速 HTTP 探測器：支援雙門戶通道 (JCBLoginServlet + JCBMainServlet)
    與 HTTP Proxy 代理，單次探測約 20~50ms。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    proxy_arg = proxy_url.strip() if proxy_url and proxy_url.strip().startswith("http") else None

    # 1. 優先探測直接登錄頁 (LOGIN_URL)
    try:
        async with session.get(LOGIN_URL, headers=headers, proxy=proxy_arg, timeout=aiohttp.ClientTimeout(total=3.5)) as resp:
            if resp.status < 500:
                text = await resp.text(errors="ignore")
                if "txtCreditCard" in text or "txtEasyCard" in text:
                    return True, "★★★ 登錄門戶已開啟！直接開放填寫 ★★★"
                if "已額滿" in text:
                    return False, "官方登錄已額滿"
                if "非開放登錄期間" not in text and resp.status == 200 and len(text) > 500:
                    return True, "★★★ 狀態變更 (疑似已開放) ★★★"
    except Exception:
        pass

    # 2. 備援探測活動首頁 (MAIN_URL - 官方常在倒數前先在主頁解禁按鈕)
    try:
        async with session.get(MAIN_URL, headers=headers, proxy=proxy_arg, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
            if resp.status >= 500:
                return False, f"伺服器壅塞 (HTTP {resp.status})"
            text = await resp.text(errors="ignore")
            if "非開放登錄期間" in text:
                return False, "非開放登錄期間"
            if "已額滿" in text:
                return False, "已額滿"
            if "JCBLoginServlet" in text or "我要登錄" in text:
                return True, "★★★ 官方活動主頁已開啟登錄按鈕！ ★★★"
            return False, "門戶尚未開放"
    except asyncio.TimeoutError:
        return False, "連線超時"
    except Exception as e:
        return False, f"探測異常: {str(e)[:30]}"

# ==============================================================================
# 6. 即時通報推播服務 (Telegram / Webhook)
# ==============================================================================
async def send_notification(title: str, content: str):
    """
    發送推播通知至 Telegram 或 LINE Notify / Webhook
    """
    settings = database.get_settings()
    tg_token = settings.get("tg_bot_token", "")
    tg_chat_id = settings.get("tg_chat_id", "")
    webhook_url = settings.get("webhook_url", "")
    
    if tg_token and tg_chat_id:
        tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        text = f"📢 *{title}*\n\n{content}"
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(tg_url, json={
                    "chat_id": tg_chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                }, timeout=aiohttp.ClientTimeout(total=5))
        except Exception as e:
            print(f"[Notify] Telegram 推播失敗: {e}")

    if webhook_url:
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(webhook_url, json={
                    "title": title,
                    "text": f"{title}\n{content}",
                    "content": f"**{title}**\n{content}"
                }, timeout=aiohttp.ClientTimeout(total=5))
        except Exception as e:
            print(f"[Notify] Webhook 推播失敗: {e}")

# ==============================================================================
# 7. JCB 極速搶登核心引擎 (JCBLoginEngine)
# ==============================================================================
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
        auto_captcha = config.get("auto_captcha", True)
        enable_ntp = config.get("enable_ntp", True)
        sprint_mode = config.get("sprint_mode", True)
        max_duration_seconds = config.get("max_duration_seconds", 0)
        retry_until = config.get("retry_until", "")
        if retry_until:
            try:
                from datetime import datetime, date
                until_str = str(retry_until).strip()
                today = date.today()
                if len(until_str.split(":")) == 2:
                    target_dt = datetime.strptime(f"{today} {until_str}:00", "%Y-%m-%d %H:%M:%S")
                else:
                    target_dt = datetime.strptime(f"{today} {until_str}", "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                diff = (target_dt - now).total_seconds()
                if diff > 0:
                    max_duration_seconds = int(diff)
                    self.log(f"⏱️ 已設定重試截止時間為 {until_str} (將持續重試約 {max_duration_seconds} 秒)")
            except Exception as e:
                self.log(f"解析截止時間警告: {e}")
        
        self.log(f"=== 啟動 JCB 並行搶登錄任務 (Session: {self.current_session_id}) ===")
        dry_run = config.get("dry_run", False)
        if dry_run:
            self.log("【🧪 演練模擬測試模式已啟動】本輪搶登將載入本機全真模擬 JCB 登錄頁面，不發送真實請求。")

        self.log(f"目標卡片數量: {len(selected_cards)} 張，多卡並行上限: {max_concurrent_workers} 組分頁")
        self.log(f"瀏覽器模式: {'無頭模式 (背景)' if headless else '可視化視窗 (Headed)'}")
        self.log(f"驗證碼自動 OCR 辨識: {'【已啟用 🤖】' if auto_captcha else '【已關閉 (人工輸入)】'}")
        
        ntp_offset = 0.0
        if enable_ntp:
            self.log("正在連線國家時間伺服器 (time.stdtime.gov.tw) 進行精密校時...")
            try:
                ntp_offset = await asyncio.to_thread(get_ntp_offset)
                self.log(f"✓ NTP 校時完成！本地時間偏差: {ntp_offset*1000:.1f} 毫秒")
            except Exception as e:
                self.log(f"NTP 校時跳過: {e}")

        # 支援 Proxy 代理伺服器設定 (Anti-IP Ban 備援)
        settings = database.get_settings()
        proxy_url = settings.get("proxy_url", "").strip()
        proxy_config = None
        if proxy_url and proxy_url.startswith("http"):
            proxy_config = {"server": proxy_url}
            self.log(f"🛡️ 已啟用防封鎖 Proxy 代理: {proxy_url}")

        start_time = time.time()

        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                proxy=proxy_config,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars"
                ]
            )
            
            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 850},
                proxy=proxy_config,
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
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head><meta charset="utf-8"><title>獨享禮遇JCB晶緻等級以上（含極緻）悠遊卡自動加值10%現金回饋優惠活動</title>
                <style>
                    body {{ font-family: sans-serif; padding: 20px; background: #f8fafc; color: #1e293b; }}
                    .box {{ max-width: 580px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                    .row {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }}
                    input.text_field {{ padding: 8px; border: 1px solid #cbd5e1; border-radius: 4px; text-align: center; font-size: 15px; font-weight: bold; width: 60px; }}
                    #send {{ display: none; background: #2563eb; color: #fff; text-decoration: none; padding: 10px 20px; border-radius: 6px; text-align: center; font-weight: bold; cursor: pointer; }}
                </style>
                </head>
                <body>
                    <div class="box">
                        <h3>獨享禮遇JCB悠遊卡自動加值10%現金回饋 (官方全真演練)</h3>
                        <form id="form1" name="form1" onsubmit="return false;">
                            <p>
                                <input type="checkbox" id="accept" name="accept" onchange="document.getElementById('input_panel').style.display = this.checked ? 'block' : 'none'; document.getElementById('send').style.display = this.checked ? 'block' : 'none';">
                                <label for="accept"><strong>我同意活動注意事項及隱私權政策條款</strong></label>
                            </p>
                            <div id="input_panel" style="display:none; margin-top:15px; padding-top:10px; border-top:1px dashed #cbd5e1;">
                                <label>請輸入JCB信用卡前6碼與後4碼：</label>
                                <div class="row">
                                    <input type="text" class="text_field" maxlength="4" id="txtCreditCard1" name="txtCreditCard1" style="width:70px;"> -
                                    <input type="text" class="text_field" maxlength="2" id="txtCreditCard2" name="txtCreditCard2" style="width:45px;"> -
                                    <input type="text" class="text_field" maxlength="4" id="txtCreditCard3" value="****" disabled style="background:#e2e8f0; width:70px;"> -
                                    <input type="text" class="text_field" maxlength="4" id="txtCreditCard4" name="txtCreditCard4" style="width:70px;">
                                </div>
                                <label>請輸入晶片悠遊卡卡號 16 碼：</label>
                                <div class="row">
                                    <input type="text" class="text_field" maxlength="4" id="txtEasyCard1" name="txtEasyCard1"> -
                                    <input type="text" class="text_field" maxlength="4" id="txtEasyCard2" name="txtEasyCard2"> -
                                    <input type="text" class="text_field" maxlength="4" id="txtEasyCard3" name="txtEasyCard3"> -
                                    <input type="text" class="text_field" maxlength="4" id="txtEasyCard4" name="txtEasyCard4">
                                </div>
                                <br>
                                <a href="javascript:void(0)" id="send" name="send" class="send" onclick="document.body.innerHTML='<div class=\\'box\\' style=\\'text-align:center;\\'><h2>登錄成功！</h2><p>恭喜您完成 2026 年度 JCB 晶片悠遊卡自動加值 10% 現金回饋活動登錄！</p><p>登錄序號：MOCK-202611209999</p></div>'; return false;">確認送出</a>
                            </div>
                        </form>
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
                
                current_interval = base_interval_ms
                if sprint_mode:
                    now_precise = time.time() + ntp_offset
                    calc_interval, stage_desc = get_sprint_interval(now_precise)
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
                        await send_notification("JCB 搶登額滿提醒", f"卡片【{card_name}】登錄時系統已顯示額滿。")
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
                // 1. 自動勾選「我同意活動注意事項及隱私權政策條款」以展開輸入面板
                const chk = document.querySelector('#accept, input[name="accept"]');
                if (chk && !chk.checked) {{
                    chk.checked = true;
                    chk.dispatchEvent(new Event('click', {{ bubbles: true }}));
                    chk.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
                const panel = document.getElementById('input_panel');
                if (panel) panel.style.display = 'block';
                const sendBtn = document.getElementById('send');
                if (sendBtn) sendBtn.style.display = 'block';

                // 2. 注入 JCB 信用卡卡號 (前6碼拆為4+2碼，後4碼注入第4欄位)
                const c1 = document.querySelector('#txtCreditCard1, input[name="txtCreditCard1"]');
                const c2 = document.querySelector('#txtCreditCard2, input[name="txtCreditCard2"]');
                const c4 = document.querySelector('#txtCreditCard4, input[name="txtCreditCard4"]');
                
                const pref = "{prefix}";
                const suff = "{suffix}";
                if (c1) {{ c1.value = pref.substring(0, 4); c1.dispatchEvent(new Event('input', {{ bubbles: true }})); c1.dispatchEvent(new Event('keyup', {{ bubbles: true }})); }}
                if (c2) {{ c2.value = pref.substring(4, 6); c2.dispatchEvent(new Event('input', {{ bubbles: true }})); c2.dispatchEvent(new Event('keyup', {{ bubbles: true }})); }}
                if (c4) {{ c4.value = suff; c4.dispatchEvent(new Event('input', {{ bubbles: true }})); c4.dispatchEvent(new Event('keyup', {{ bubbles: true }})); }}

                // 備援：若頁面為舊版或單一信用卡欄位
                const fallbackC1 = document.querySelector('input[name="txtCard1"]');
                if (fallbackC1) fallbackC1.value = pref;
                const fallbackC2 = document.querySelector('input[name="txtCard2"]');
                if (fallbackC2) fallbackC2.value = suff;

                // 3. 注入悠遊卡 16 碼 (4碼一組)
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
            
            if auto_captcha:
                self.log(f"[{card_name}] 🤖 正在掃描並辨識圖形驗證碼...")
                captcha_code = await recognize_captcha_from_page(page)
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
                    submit_js = """
                    () => {
                        const btn = document.querySelector('#send, .send, a[onclick*="Submit_Check"], button[type="submit"], input[type="submit"], input[value*="登錄"], input[value*="送出"]');
                        if (btn) btn.click();
                    }
                    """
                    await page.evaluate(submit_js)
                else:
                    self.log(f"[{card_name}] 提示: 網頁可能無驗證碼或由使用者手動輸入")
            else:
                self.log(f"[{card_name}] 使用者設定為手動輸入驗證碼，請在視窗中輸入...")

            await send_notification("JCB 網頁已開放！", f"卡片【{card_name}】已自動填寫卡號，請確認送出！")
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
                    await send_notification("🎉 JCB 登錄成功！", f"太棒了！卡片【{card_name}】已成功完成本月搶登錄！")
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
                    await send_notification("JCB 搶登額滿提醒", f"卡片【{card_name}】搶登時系統已額滿。")
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
