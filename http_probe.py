import aiohttp
import asyncio
from typing import Tuple

TARGET_URL = "https://ezweb.easycard.com.tw/Event01/JCBLoginServlet"

async def fast_http_check(session: aiohttp.ClientSession) -> Tuple[bool, str]:
    """
    輕量化極速 HTTP 探測器 (不載入字型/CSS/圖片)：
    單次探測約 20~50ms，捕捉開門瞬間。
    回傳 (is_open: bool, message: str)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        async with session.get(TARGET_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status >= 500:
                return False, f"伺服器壅塞 (HTTP {resp.status})"
            text = await resp.text(errors="ignore")
            if "非開放登錄期間" in text:
                return False, "非開放登錄期間"
            if "已額滿" in text:
                return False, "已額滿"
            # 偵測到開放表單特徵
            if "txtCreditCard" in text or "txtEasyCard" in text or "JCB" in text:
                return True, "★★★ 登錄門戶已開啟！ ★★★"
            return True, "狀態變更 (疑似已開放)"
    except asyncio.TimeoutError:
        return False, "連線超時"
    except Exception as e:
        return False, f"探測異常: {str(e)[:30]}"
