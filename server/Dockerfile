FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 先只拷 pyproject.toml 安装依赖（依赖不变时该层走缓存，不用每次下载）
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[postgres,cos,robot]"

# 再拷贝源码（.dockerignore 已排除 .env / var / tests / docs / logs 等）
COPY . .

EXPOSE 8000 8081
