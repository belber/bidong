FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 源码（.dockerignore 已排除 .env / var / tests / docs 等）
COPY . .

# 生产依赖：Postgres 驱动 + COS + 机器人（qrcode）
RUN pip install --no-cache-dir ".[postgres,cos,robot]"

EXPOSE 8000 8081
