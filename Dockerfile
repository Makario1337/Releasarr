FROM python:3.9-slim

WORKDIR /app
COPY ./requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:1337", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker"]