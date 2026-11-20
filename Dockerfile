# 使用官方 Playwright 預載環境鏡像，直接具備 Chromium 與所有必要 GUI/字型依賴
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HEADLESS_DEFAULT=true

WORKDIR /app

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式程式碼
COPY . .

# Cloud Run 預設監聽 PORT 環境變數 (預設 8080)
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
