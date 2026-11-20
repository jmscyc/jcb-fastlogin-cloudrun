import asyncio
import os
import sys
import argparse
import database
import notify
from login_engine import engine

async def main():
    parser = argparse.ArgumentParser(description="JCB FastLogin CLI Runner for GitHub Actions")
    parser.add_argument("--interval", type=int, default=500, help="Retry interval in ms")
    parser.add_argument("--workers", type=int, default=2, help="Max concurrent workers")
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

    if not selected_cards:
        print("[ERROR] 目前卡片庫中沒有任何選取的卡片！")
        print("💡 請在 GitHub 儲存庫 Settings -> Secrets and variables -> Actions 新增名為 JCB_CARDS_JSON 的 Secret 填入卡片 JSON")
        sys.exit(1)

    print(f"[INFO] 本次即將搶登之卡片共 {len(selected_cards)} 張：")
    for c in selected_cards:
        print(f" - {c['name']} (尾號 {c['credit_card_suffix']})")

    engine.subscribe_logs(lambda msg: print(msg, flush=True))

    config = {
        "headless": True,
        "retry_interval_ms": args.interval,
        "max_concurrent_workers": args.workers
    }

    await notify.send_notification("🚀 JCB 雲端搶登任務啟動", f"GitHub Actions 雲端已開始執行搶登，共 {len(selected_cards)} 張卡片正在監測中！")
    await engine.run_task(selected_cards, config)
    print("=== [GitHub Actions 任務結束] ===")

if __name__ == "__main__":
    asyncio.run(main())
