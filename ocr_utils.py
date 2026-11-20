import base64
import re
from typing import Optional

def solve_captcha_image_sync(image_bytes: bytes) -> str:
    """
    驗證碼解析器：
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

async def recognize_captcha_from_page(page) -> Optional[str]:
    """
    自動在 Playwright 頁面上尋找驗證碼圖片元素，擷取圖片並執行解析。
    支援常見 id: #imgCode, #captchaImg, #picCode, 或含 Captcha / Validate 的 img 標籤。
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
