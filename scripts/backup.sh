#!/usr/bin/env bash
# Consistent MySQL backup of the running compose stack (no downtime: --single-transaction on InnoDB).
#   ./scripts/backup.sh                 # writes ./backups/aifp-<UTC timestamp>.sql.gz (+ .sha256)
# Env: BACKUP_DIR (default ./backups), BACKUP_KEEP_DAYS (default 14)
# Run it from cron/Task Scheduler (e.g. hourly) and COPY the files off the host (object storage, another region):
# a backup on the same disk as the database is not a backup.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$OUT_DIR"
file="$OUT_DIR/aifp-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"

docker compose exec -T db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --routines --triggers --no-tablespaces --default-character-set=utf8mb4 \
  --set-gtid-purged=OFF "$MYSQL_DATABASE"' 2>/dev/null | gzip -9 > "$file.tmp"

# Refuse to keep a backup that is empty, corrupt, or missing core tables.
gzip -t "$file.tmp"
zcat "$file.tmp" | grep -q 'CREATE TABLE `users`' || { rm -f "$file.tmp"; echo "backup looks incomplete" >&2; exit 1; }
zcat "$file.tmp" | grep -q 'CREATE TABLE `credit_transactions`' || { rm -f "$file.tmp"; echo "backup looks incomplete" >&2; exit 1; }

mv "$file.tmp" "$file"
( cd "$OUT_DIR" && sha256sum "$(basename "$file")" > "$(basename "$file").sha256" )
find "$OUT_DIR" -name 'aifp-*.sql.gz*' -mtime +"$KEEP_DAYS" -delete
echo "backup ok: $file ($(du -h "$file" | cut -f1))"
