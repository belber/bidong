#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# ================= 部署配置 =================
# 真实地址不进仓库：从本目录未跟踪的 deploy.env 读取（已在 .gitignore）。
# 首次使用先创建 deploy.env，内容示例：
#   REMOTE_USER=ubuntu
#   REMOTE_HOST=1.2.3.4
#   REMOTE_PORT=22
#   REMOTE_DIR=/opt/bidong/server
if [[ -f deploy.env ]]; then
  # shellcheck disable=SC1091
  source ./deploy.env
fi

REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_DIR="${REMOTE_DIR:-/opt/bidong/server}"
ENV_FILE="${ENV_FILE:-.env.prod}"

if [[ -z "$REMOTE_HOST" ]]; then
  echo "缺少 REMOTE_HOST：请在本目录创建 deploy.env 并填写服务器地址，例如 REMOTE_HOST=1.2.3.4" >&2
  exit 1
fi
# ===========================================

# 参数：--up 远端重建启动；--env 顺带上传密钥文件 .env.prod
DO_UP=0
DO_ENV=0
for arg in "$@"; do
  case "$arg" in
    --up) DO_UP=1 ;;
    --env) DO_ENV=1 ;;
  esac
done

SSH_CMD=(ssh -p "$REMOTE_PORT" "${REMOTE_USER}@${REMOTE_HOST}")

echo ">>> 确保远端目录存在"
"${SSH_CMD[@]}" "mkdir -p ${REMOTE_DIR}"

echo ">>> 同步 server/ -> ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
rsync -az --progress \
  -e "ssh -p ${REMOTE_PORT}" \
  --exclude '.venv' \
  --exclude 'var' \
  --exclude 'logs' \
  --exclude '*.egg-info' \
  --exclude 'tests' \
  --exclude '.git' \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude '.env.*' \
  ./server/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

if [[ "$DO_ENV" == "1" ]]; then
  echo ">>> 上传密钥文件 ${ENV_FILE}"
  scp -P "$REMOTE_PORT" "./server/${ENV_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/${ENV_FILE}"
fi

if [[ "$DO_UP" == "1" ]]; then
  echo ">>> 远端重建并启动（ENV_FILE=${ENV_FILE}）"
  "${SSH_CMD[@]}" "cd ${REMOTE_DIR} && APP_ENV_FILE=${ENV_FILE} docker compose up -d --build"
else
  echo ">>> 同步完成。"
  echo "    如需重建并启动：${0} --up"
  echo "    首次或改了密钥文件：${0} --env --up"
fi
