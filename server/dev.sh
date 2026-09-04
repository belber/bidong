#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# 一键同时启动 FastAPI 服务器和机器人 worker；Ctrl+C 一起停止
trap 'kill 0' INT TERM

# 统一注入到所有进程，避免 API 与管理端环境变量不一致导致开关取值差异
export ENABLE_WATERMARKED_VIDEO="true"
export ENABLE_CLEAN_VIDEO="true"
export ENABLE_AUDIO="true"

.venv/bin/python -m uvicorn app.main:app --reload &

.venv/bin/python -m uvicorn app.admin_app:app --host 0.0.0.0 --port "${ADMIN_PORT:-8081}" --reload &

.venv/bin/python -m app.robot.worker &

echo "已启动：uvicorn(API:8000) + 管理端(:${ADMIN_PORT:-8081}) + 机器人 worker。按 Ctrl+C 同时停止。"
wait
