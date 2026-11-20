@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JCB 悠遊卡自動搶登錄系統 Pro

echo ========================================================
echo        JCB 悠遊卡自動搶登錄系統 (JCB FastLogin Pro)
echo ========================================================
echo 正在檢查執行環境與套件，請稍候...
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 電腦尚未安裝 Python 或未勾選 Add Python to PATH！
    echo 請先至 https://www.python.org 下載安裝 Python 並重試。
    pause
    exit /b
)

echo [1/3] 檢查 Python 相關套件...
python -m pip install fastapi uvicorn playwright jinja2 aiohttp pydantic

echo.
echo [2/3] 檢查 Playwright 瀏覽器核心...
python -m playwright install chromium

echo.
echo [3/3] 系統就緒，正在啟動後台並開啟瀏覽器...
echo.

start "" http://localhost:8088

python -m uvicorn main:app --host 0.0.0.0 --port 8088
pause
