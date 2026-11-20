FROM python:3.11-slim

# tzdata：scheduler 用 ZoneInfo("Asia/Hong_Kong")，slim 镜像不带时区数据，缺了会抛
# ZoneInfoNotFoundError 导致定时器建不起来（每日 09:00 抓取失效）。
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
COPY app ./app
COPY alembic.ini ./
COPY app/db/migrations ./app/db/migrations

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
