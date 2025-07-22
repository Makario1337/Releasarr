FROM python:3.13-slim-bullseye

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["/bin/bash", "-c", "gunicorn app.main:app --bind 0.0.0.0:${APP_PORT:-1337} --workers ${APP_WORKERS:-1} --worker-class uvicorn.workers.UvicornWorker"]

EXPOSE 1337

VOLUME ["/config", "/logs"]