import asyncio
import os
import sys
import argparse
import database
from login_engine import engine, send_notification

# 預設卡片範本（若未提供 Secret 時自動使用此處設定）
DEFAULT_CARDS = [
    {
        "name": "富邦JCB",
        "credit_card_prefix": "356890",
        "credit_card_suffix": "1234",
        "easycard_number": "0123456789012345",
        "is_selected": 1,
        "priority": 10
    }
]

async def main():
    parser = argparse.ArgumentParser(description="JCB FastLogin CLI Runner for GitHub Actions")
    parser.add_argument("--interval", type=int, default=500, help="Retry interval in ms")
    parser.add_argument("--workers", type=int, default=2, help="Max concurrent workers")
    parser.add_argument("--timeout", type=int, default=600, help="Max duration in seconds")
    parser.add_argument("--no-captcha", action="store_true", help="Disable auto captcha recognition")
    parser.add_argument("--no-ntp", action="store_true", help="Disable NTP network sync")
    parser.add_argument("--no-sprint", action="store_true", help="Disable dynamic sprint mode")
    args = parser.parse_args()

    print("=== [GitHub Actions 雲端自動搶登任務啟動] ===")
    database.init_db()

    # 讀取 Secrets 環境變數
    cards_env = os.environ.get("JCB_CARDS_JSON", "")
    tg_token = os.environ.get("TG_BOT_TOKEN", "")
    tg_chat_id = os.environ.get("TG_CHAT_ID", "")
    webhook_url = os.environ.get("WEBHOOK_URL", "")

    if tg_token:
        database.update_setting("tg_bot_token", tg_token)
    if tg_chat_id:
        database.update_setting("tg_chat_id", tg_chat_id)
    if webhook_url:
        database.update_setting("webhook_url", webhook_url)

    if cards_env:
        try:
            print("[INFO] 偵測到環境變數 JCB_CARDS_JSON，正在載入卡片庫...")
            database.import_cards_json(cards_env)
        except Exception as e:
            print(f"[WARN] 載入環境變數卡片失敗: {e}")

    cards = database.get_cards()
    selected_cards = [c for c in cards if c["is_selected"] == 1]

    # 若資料庫無卡片，自動載入預設卡片庫
    if not selected_cards:
        print("[INFO] 資料庫為空，自動載入預設卡片設定...")
        for c in DEFAULT_CARDS:
            database.add_card(c["name"], c["credit_card_prefix"], c["credit_card_suffix"], c["easycard_number"], c.get("priority", 0))
        cards = database.get_cards()
        selected_cards = [c for c in cards if c["is_selected"] == 1]

    print(f"[INFO] 本次即將搶登之卡片共 {len(selected_cards)} 張：")
    for c in selected_cards:
        print(f" - {c['name']} (尾號 {c['credit_card_suffix']})")

    # engine.log 內部已包含 print(formatted)，不需重複 subscribe_logs(print)

    config = {
        "headless": True,
        "retry_interval_ms": args.interval,
        "max_concurrent_workers": args.workers,
        "max_duration_seconds": args.timeout,
        "auto_captcha": not args.no_captcha,
        "enable_ntp": not args.no_ntp,
        "sprint_mode": not args.no_sprint
    }

    await send_notification("🚀 JCB 雲端搶登任務啟動", f"GitHub Actions 雲端已開始執行搶登，共 {len(selected_cards)} 張卡片正在監測中！")
    await engine.run_task(selected_cards, config)
    print("=== [GitHub Actions 任務結束] ===")

if __name__ == "__main__":
    asyncio.run(main())
