FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HEADLESS_DEFAULT=true

# Hugging Face 要求容器內不要以 root 執行，建議建立使用者 user (UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

# 安裝依賴
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 複製應用程式程式碼
COPY --chown=user:user . .

# Hugging Face Spaces 預設對外暴露 Port 7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 7860"]
