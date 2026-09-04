#!/usr/bin/env bash
set -euo pipefail

# 数据库备份（在服务器 server/ 目录下执行）
# 建议 crontab 每天跑一次，例如：
#   0 3 * * * cd /opt/bidong/server && ./backup_db.sh >> /opt/bidong/backups/backup.log 2>&1
#
# 备份目录可用环境变量覆盖：BACKUP_DIR（默认 /opt/bidong/backups）
# 保留天数：KEEP_DAYS（默认 14）

cd "$(dirname "$0")"

ENV_FILE=".env.prod"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "找不到 ${ENV_FILE}，请在 server/ 目录下运行"
  exit 1
fi

POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | tail -1 | cut -d= -f2-)
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | tail -1 | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | tail -1 | cut -d= -f2-)

BACKUP_DIR="${BACKUP_DIR:-/opt/bidong/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$BACKUP_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/bidong_${POSTGRES_DB:-db}_${STAMP}.sql.gz"

echo ">>> 备份数据库 ${POSTGRES_DB:-db} -> ${OUT}"
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db pg_dump -U "$POSTGRES_USER" "${POSTGRES_DB:-db}" | gzip > "$OUT"
ls -lh "$OUT"

# 清理超过 KEEP_DAYS 天的备份
find "$BACKUP_DIR" -maxdepth 1 -name 'bidong_*.sql.gz' -mtime "+${KEEP_DAYS}" -delete
echo ">>> 完成（保留 ${KEEP_DAYS} 天内的备份）"
