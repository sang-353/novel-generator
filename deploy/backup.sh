#!/usr/bin/env bash
# ============================================================================
# 小说生成器 —— 备份脚本（由 /etc/cron.d/novel-backup 每天调用，也可手动执行）
#
#   sudo bash /opt/novel-generator/deploy/backup.sh
#
# 备份内容：novels/（全部小说 + 回收站 + 章节备份）与 config.json
# 备份文件权限是 600/700：config.json 里有明文 API Key，不能让别的用户读到。
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/novel-generator}"
DEST="${DEST:-/var/backups/novel-generator}"
KEEP_DAYS="${KEEP_DAYS:-30}"

[[ -f "${APP_DIR}/config.json" ]] || { echo "找不到 ${APP_DIR}/config.json" >&2; exit 1; }

umask 077
mkdir -p "${DEST}"

STAMP="$(date +%F-%H%M)"
OUT="${DEST}/novel-${STAMP}.tar.gz"

tar -czf "${OUT}" -C "${APP_DIR}" novels config.json

# 只保留最近 KEEP_DAYS 天
find "${DEST}" -maxdepth 1 -name 'novel-*.tar.gz' -type f -mtime "+${KEEP_DAYS}" -delete

SIZE="$(du -h "${OUT}" | cut -f1)"
COUNT="$(find "${DEST}" -maxdepth 1 -name 'novel-*.tar.gz' | wc -l)"
echo "$(date '+%F %T')  备份完成 ${OUT} (${SIZE})，目录内共 ${COUNT} 份"
