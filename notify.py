import asyncio
import aiohttp
import database

async def send_notification(title: str, content: str):
    """
    發送推播通知至 Telegram 或 LINE Notify / Webhook
    """
    settings = database.get_settings()
    tg_token = settings.get("tg_bot_token", "")
    tg_chat_id = settings.get("tg_chat_id", "")
    webhook_url = settings.get("webhook_url", "")
    
    # Telegram 推播
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

    # 自訂 Webhook (支援 Discord, Slack, 或自建 Hook)
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
