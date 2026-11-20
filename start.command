#!/bin/bash
cd "$(dirname "$0")"

echo "========================================================"
echo "       JCB 悠遊卡自動搶登錄系統 (JCB FastLogin Pro)        "
echo "========================================================"
echo "正在檢查執行環境與套件..."

python3 -m pip install -q fastapi uvicorn playwright jinja2 aiohttp pydantic 2>/dev/null
python3 -m playwright install chromium 2>/dev/null

echo "[✓] 正在啟動伺服器並自動開啟瀏覽器..."
(sleep 2 && open http://localhost:8088) &
python3 -m uvicorn main:app --host 0.0.0.0 --port 8088
