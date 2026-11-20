import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

import database
import notify
from login_engine import engine

app = FastAPI(title="JCB 悠遊卡自動搶登錄系統 Pro")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 資料模型
class CardCreateRequest(BaseModel):
    name: str
    credit_card_prefix: str
    credit_card_suffix: str
    easycard_number: str
    priority: Optional[int] = 0

class CardToggleRequest(BaseModel):
    card_id: int
    is_selected: bool

class CardPriorityRequest(BaseModel):
    card_id: int
    priority: int

class TaskStartRequest(BaseModel):
    headless: Optional[bool] = False
    retry_interval_ms: Optional[int] = 500
    max_concurrent_workers: Optional[int] = 2
    scheduled_time: Optional[str] = None # 預約排程時間字串: "YYYY-MM-DD HH:MM:SS"

class SettingsUpdateRequest(BaseModel):
    tg_bot_token: Optional[str] = ""
    tg_chat_id: Optional[str] = ""
    webhook_url: Optional[str] = ""

# 即時日誌快取
log_messages = []
scheduled_task_handle = None

def on_new_log(msg: str):
    log_messages.append(msg)
    if len(log_messages) > 300:
        log_messages.pop(0)

engine.subscribe_logs(on_new_log)

@app.on_event("startup")
def startup_event():
    database.init_db()

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/cards")
def get_cards_list():
    cards = database.get_cards_with_stats()
    return {"status": "ok", "cards": cards}

@app.post("/api/cards")
def create_card(card: CardCreateRequest):
    prefix = card.credit_card_prefix.strip()
    suffix = card.credit_card_suffix.strip()
    easy = card.easycard_number.strip().replace("-", "").replace(" ", "")
    
    if len(prefix) != 6 or not prefix.isdigit():
        raise HTTPException(status_code=400, detail="信用卡前 6 碼必須為 6 位數字")
    if len(suffix) != 4 or not suffix.isdigit():
        raise HTTPException(status_code=400, detail="信用卡後 4 碼必須為 4 位數字")
    if len(easy) != 16 or not easy.isdigit():
        raise HTTPException(status_code=400, detail="悠遊卡卡號必須為 16 位數字")
        
    card_id = database.add_card(card.name, prefix, suffix, easy, card.priority or 0)
    return {"status": "ok", "card_id": card_id}

@app.delete("/api/cards/{card_id}")
def delete_card_endpoint(card_id: int):
    database.delete_card(card_id)
    return {"status": "ok"}

@app.post("/api/cards/toggle")
def toggle_card_selection(data: CardToggleRequest):
    database.update_card_selection(data.card_id, data.is_selected)
    return {"status": "ok"}

@app.post("/api/cards/priority")
def set_priority(data: CardPriorityRequest):
    database.update_card_priority(data.card_id, data.priority)
    return {"status": "ok"}

@app.get("/api/cards/export")
def export_cards():
    json_data = database.export_cards_json()
    return PlainTextResponse(json_data, media_type="application/json")

@app.post("/api/cards/import")
def import_cards(body: Dict[str, Any] = Body(...)):
    raw_json = body.get("json_data", "")
    try:
        count = database.import_cards_json(raw_json)
        return {"status": "ok", "count": count, "message": f"成功匯入 {count} 張卡片！"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"匯入格式錯誤: {str(e)}")

@app.get("/api/settings")
def get_settings():
    return {"status": "ok", "settings": database.get_settings()}

@app.post("/api/settings")
def save_settings(data: SettingsUpdateRequest):
    if data.tg_bot_token is not None:
        database.update_setting("tg_bot_token", data.tg_bot_token.strip())
    if data.tg_chat_id is not None:
        database.update_setting("tg_chat_id", data.tg_chat_id.strip())
    if data.webhook_url is not None:
        database.update_setting("webhook_url", data.webhook_url.strip())
    return {"status": "ok", "message": "設定已儲存"}

@app.post("/api/settings/test-notify")
async def test_notify():
    await notify.send_notification("JCB 搶登助手 - 測試推播", "這是一則測試通知，代表您的推播設定運作正常！🎉")
    return {"status": "ok", "message": "測試通知已發送！"}

@app.post("/api/records/clear-session")
def clear_current_session():
    database.clear_current_session_records()
    return {"status": "ok", "message": "已清除本次執行紀錄"}

@app.post("/api/records/clear-yearly")
def clear_yearly():
    database.clear_card_yearly_records()
    return {"status": "ok", "message": "已重置今年度登錄次數統計"}

@app.post("/api/records/clear-all")
def clear_all():
    database.clear_all_records()
    return {"status": "ok", "message": "已清除所有登錄歷史紀錄"}

@app.post("/api/task/start")
async def start_task(config: TaskStartRequest):
    global scheduled_task_handle
    if engine.is_running:
        return {"status": "error", "message": "任務正在執行中！"}
        
    cards = database.get_cards()
    selected_cards = [c for c in cards if c["is_selected"] == 1]
    
    if not selected_cards:
        return {"status": "error", "message": "請先至少勾選一張要搶登的卡片！"}

    # 如果有設定預約時間
    if config.scheduled_time:
        try:
            target_dt = datetime.strptime(config.scheduled_time.strip(), "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            delay_seconds = (target_dt - now).total_seconds()
            
            if delay_seconds > 0:
                engine.log(f"[預約排程] 已設定於 {config.scheduled_time} (約 {int(delay_seconds)} 秒後) 自動啟動！")
                
                async def scheduled_runner():
                    await asyncio.sleep(delay_seconds)
                    engine.log("[預約排程] 時間已到，立即喚醒執行引擎！")
                    await engine.run_task(selected_cards, config.dict())
                    
                scheduled_task_handle = asyncio.create_task(scheduled_runner())
                return {"status": "ok", "message": f"已預約排程於 {config.scheduled_time} 自動開跑"}
            else:
                engine.log("[預約排程] 指定時間已過，立即啟動任務！")
        except ValueError:
            raise HTTPException(status_code=400, detail="預約時間格式錯誤，請使用 YYYY-MM-DD HH:MM:SS")

    # 立即啟動非同步任務
    asyncio.create_task(engine.run_task(selected_cards, config.dict()))
    return {"status": "ok", "message": f"已立即啟動搶登任務，共 {len(selected_cards)} 張卡片"}

@app.post("/api/task/stop")
def stop_task():
    global scheduled_task_handle
    if scheduled_task_handle and not scheduled_task_handle.done():
        scheduled_task_handle.cancel()
        engine.log("[預約排程] 已取消預約定時排程。")
    if engine.is_running:
        engine.stop()
    return {"status": "ok", "message": "已發送停止指令"}

@app.get("/api/task/status")
def task_status():
    return {
        "is_running": engine.is_running,
        "logs": log_messages[-40:]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8088, reload=True)
