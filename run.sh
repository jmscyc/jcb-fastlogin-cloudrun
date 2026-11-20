#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  啟動 JCB 悠遊卡自動搶登錄系統 (FastLogin) "
echo "========================================="
echo "正在檢查依賴套件..."

python3 -m pip install -q fastapi uvicorn playwright jinja2 aiohttp pydantic 2>/dev/null || true
python3 -m playwright install chromium 2>/dev/null || true

# 在背景延遲 2 秒自動打開瀏覽器
(sleep 2 && (which xdg-open >/dev/null && xdg-open http://localhost:8088 || open http://localhost:8088 2>/dev/null || true)) &

echo "本地 Web 控制台即將於 http://localhost:8088 啟動..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8088
