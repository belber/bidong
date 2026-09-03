#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# 一键同时启动 FastAPI 服务器和机器人 worker；Ctrl+C 一起停止
trap 'kill 0' INT TERM

ENABLE_WATERMARKED_VIDEO=true \
ENABLE_CLEAN_VIDEO=true \
ENABLE_AUDIO=true \
  .venv/bin/python -m uvicorn app.main:app --reload &

.venv/bin/python -m app.robot.worker &

echo "已启动：uvicorn(API) + 机器人 worker。按 Ctrl+C 同时停止。"
wait
