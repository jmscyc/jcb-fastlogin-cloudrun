import asyncio
import os
import sys
import json
from login_engine import JCBLoginEngine
import database
import notify

async def main():
    print("=== [GitHub Actions 雲端自動搶登任務啟動] ===")
    database.init_db()
    
    # 支援由環境變數傳入卡片資料 (安全性高，不需硬編碼卡號)
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
        print("[ERROR] 目前卡片庫中沒有任何選取的卡片！請確認資料庫或設定 JCB_CARDS_JSON 環境變數。")
        sys.exit(1)
        
    print(f"[INFO] 本次即將搶登之卡片共 {len(selected_cards)} 張：")
    for c in selected_cards:
        print(f" - {c['name']} (尾號 {c['credit_card_suffix']})")
        
    config = {
        "headless": True, # 雲端必定使用無頭模式
        "retry_interval_ms": int(os.environ.get("RETRY_INTERVAL_MS", "400")),
        "max_concurrent_workers": int(os.environ.get("MAX_WORKERS", "3"))
    }
    
    engine = JCBLoginEngine()
    
    # 發送啟動推播通知
    await notify.send_notification("🚀 JCB 雲端搶登任務啟動", f"GitHub Actions 雲端已開始執行搶登，共 {len(selected_cards)} 張卡片正在監測中！")
    
    await engine.run_task(selected_cards, config)
    
    print("=== [GitHub Actions 任務結束] ===")

if __name__ == "__main__":
    asyncio.run(main())
