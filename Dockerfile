FROM python:3.13-bullseye

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["/bin/bash", "-c", "gunicorn app.main:app --bind 0.0.0.0:${APP_PORT:-1337} --workers ${APP_WORKERS:-1} --worker-class uvicorn.workers.UvicornWorker"]

EXPOSE 1337