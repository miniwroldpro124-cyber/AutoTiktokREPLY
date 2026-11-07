FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WORKER_HOST=0.0.0.0 \
    WORKER_PORT=8787 \
    BOT_DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY tiktok_selfbot.py worker.py ./
RUN mkdir -p /app/data

VOLUME ["/app/data"]
EXPOSE 8787

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=8).status==200 else 1)"

CMD ["python", "worker.py"]
