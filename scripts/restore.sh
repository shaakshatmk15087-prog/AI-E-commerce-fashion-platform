#!/usr/bin/env bash
# Restore a backup INTO THE LIVE DATABASE (destructive: it replaces current data).
#   ./scripts/restore.sh backups/aifp-20261123T101500Z.sql.gz
# Stop the app first so nothing writes while restoring:  docker compose stop backend scheduler web
# Afterwards:  docker compose up -d   (the migrate service reapplies any newer migrations)
set -euo pipefail
cd "$(dirname "$0")/.."

file="${1:?usage: restore.sh <backup.sql.gz>}"
[ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
[ -f "$file.sha256" ] && ( cd "$(dirname "$file")" && sha256sum -c "$(basename "$file").sha256" )
gzip -t "$file"

if [ "${FORCE:-0}" != "1" ]; then
  read -r -p "This REPLACES the live database with $file. Type RESTORE to continue: " ans
  [ "$ans" = "RESTORE" ] || { echo "aborted"; exit 1; }
fi

docker compose exec -T db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS \`$MYSQL_DATABASE\`; CREATE DATABASE \`$MYSQL_DATABASE\` CHARACTER SET utf8mb4;"' 2>/dev/null
zcat "$file" | docker compose exec -T db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 "$MYSQL_DATABASE"' 2>/dev/null
echo "restored from $file"
