#!/usr/bin/env bash
# Prove a backup is restorable WITHOUT touching live data: restore it into a scratch database, compare it with the live one,
# then drop the scratch database. Schedule this (e.g. weekly) - an untested backup is a hope, not a backup.
#   ./scripts/verify-restore.sh                       # newest file in ./backups
#   ./scripts/verify-restore.sh backups/aifp-....sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${BACKUP_DIR:-./backups}"
file="${1:-$(ls -1t "$OUT_DIR"/aifp-*.sql.gz 2>/dev/null | head -1)}"
[ -n "$file" ] && [ -f "$file" ] || { echo "no backup found" >&2; exit 1; }
[ -f "$file.sha256" ] && ( cd "$(dirname "$file")" && sha256sum -c "$(basename "$file").sha256" >/dev/null )
gzip -t "$file"

SCRATCH="aifp_verify_$$"
sql() { docker compose exec -T db sh -c "exec mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -B $1" 2>/dev/null; }
cleanup() { sql "-e 'DROP DATABASE IF EXISTS \`$SCRATCH\`'" || true; }
trap cleanup EXIT

sql "-e 'CREATE DATABASE \`$SCRATCH\` CHARACTER SET utf8mb4'"
zcat "$file" | docker compose exec -T db sh -c "exec mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" --default-character-set=utf8mb4 $SCRATCH" 2>/dev/null

live_db="$(docker compose exec -T db sh -c 'printf %s "$MYSQL_DATABASE"')"
fail=0
tables="$(sql "-e \"SELECT table_name FROM information_schema.tables WHERE table_schema='$live_db' ORDER BY 1\"")"
restored_tables="$(sql "-e \"SELECT table_name FROM information_schema.tables WHERE table_schema='$SCRATCH' ORDER BY 1\"")"
[ "$tables" = "$restored_tables" ] || { echo "FAIL: table lists differ"; fail=1; }

# Row counts of the tables that matter most. (Live may be slightly ahead of the backup; behind is the failure we look for.)
for t in users orders payments credit_transactions wallets reward_transactions consultations audit_logs; do
  live="$(sql "-e 'SELECT COUNT(*) FROM \`$live_db\`.\`$t\`'" | tr -d '\r')"
  rest="$(sql "-e 'SELECT COUNT(*) FROM \`$SCRATCH\`.\`$t\`'" | tr -d '\r')"
  printf '  %-22s live=%-8s restored=%s\n' "$t" "$live" "$rest"
  [ "$rest" -le "$live" ] || { echo "FAIL: $t restored more rows than live?"; fail=1; }
done

# (No backticks inside these double quotes: the remote sh would treat them as command substitution.)
# Integrity of the money ledgers inside the restored copy: cached balances must equal the ledger sums.
bad="$(sql "-e \"SELECT COUNT(*) FROM $SCRATCH.wallets w WHERE w.daily_balance <> COALESCE((SELECT SUM(amount) FROM $SCRATCH.credit_transactions t WHERE t.wallet_id=w.id AND t.credit_type='daily'),0) OR w.super_balance <> COALESCE((SELECT SUM(amount) FROM $SCRATCH.credit_transactions t WHERE t.wallet_id=w.id AND t.credit_type='super'),0)\"" | tr -d '\r')"
[ "$bad" = "0" ] || { echo "FAIL: $bad wallet(s) disagree with their ledger in the backup"; fail=1; }

[ "$fail" = "0" ] && echo "verify-restore OK: $file is restorable and consistent" || { echo "verify-restore FAILED"; exit 1; }
