# 固定 whisper.cpp v1.8.2；仅CPU，使用静态内部库避免运行时路径问题。
FROM debian:bookworm-slim AS whisper-build
RUN apt-get update && apt-get install -y --no-install-recommends git cmake make g++ ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/ggml-org/whisper.cpp.git /src && cd /src && git checkout 4979e04f5dcaccb36057e059bbaed8a2f5288315
RUN cmake -S /src -B /src/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_BLAS=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_TESTS=OFF && cmake --build /src/build --target whisper-cli -j 1

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=whisper-build /src/build/bin/whisper-cli /usr/local/bin/whisper-cli

WORKDIR /app

# 先只拷 pyproject.toml 安装依赖（依赖不变时该层走缓存，不用每次下载）
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[postgres,cos,robot,asr]"

# 再拷贝源码（.dockerignore 已排除 .env / var / tests / docs / logs 等）
COPY . .

EXPOSE 8000 8081
