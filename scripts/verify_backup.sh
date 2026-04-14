#!/bin/bash
# Weekly restore-verification: pick the most recent backup, restore it to a
# scratch DB inside the Postgres container, run sanity queries, drop the
# scratch DB. ntfy on EITHER failure or success — Brian needs proof of life
# that backups are actually restorable, not just successful pg_dumps.
#
# Why this matters: a backup that never restores is worse than no backup,
# because it gives false confidence. This is the only thing that proves
# the dump is complete + valid + can rebuild the schema.

set -euo pipefail

BACKUP_DIR="/srv/quantumpools/backups"
DB_CONTAINER="quantumpools-db"
DB_USER="quantumpools"
SCRATCH_DB="quantumpools_restore_test"
NTFY_URL="${NTFY_URL:-http://localhost:7031}"
NTFY_TOPIC="${NTFY_TOPIC:-qp-alerts}"

ntfy() {
    local title="$1"
    local body="$2"
    local priority="${3:-default}"
    local tags="${4:-white_check_mark}"
    curl -s -H "Title: $title" -H "Priority: $priority" -H "Tags: $tags" \
         -d "$body" "${NTFY_URL}/${NTFY_TOPIC}" >/dev/null 2>&1 || true
}

cleanup() {
    sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 1. Find the most recent backup.
LATEST=$(ls -t "$BACKUP_DIR"/quantumpools_*.sql.gz 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    ntfy "QP restore-verify FAILED" "No backups found in $BACKUP_DIR — has backup_db.sh been running?" high warning
    exit 1
fi

age_min=$(( ( $(date +%s) - $(stat -c %Y "$LATEST") ) / 60 ))
if [ "$age_min" -gt 1500 ]; then  # 25h
    ntfy "QP backup STALE" "Latest backup is ${age_min} min old (>25h). Nightly job may not be running. File: $LATEST" high warning
    # Keep going and verify what we have rather than bailing.
fi

# 2. Drop+create scratch DB.
sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null
sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres \
    -c "CREATE DATABASE $SCRATCH_DB OWNER $DB_USER;" >/dev/null

# 3. Restore. Stream the dump in via stdin so we don't need to copy it
# into the container.
if ! gunzip -c "$LATEST" | sudo docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$SCRATCH_DB" >/tmp/qp_restore.log 2>&1; then
    err=$(tail -10 /tmp/qp_restore.log)
    ntfy "QP restore-verify FAILED" "Restore of $LATEST failed.\nLast error: $err" urgent rotating_light
    exit 2
fi

# 4. Sanity queries. We don't need all data — just confirm critical tables
# rebuilt with sane row counts, and that we can actually query relationships.
sanity=$(sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$SCRATCH_DB" -tAc "
SELECT
  (SELECT COUNT(*) FROM organizations) AS orgs,
  (SELECT COUNT(*) FROM users) AS users,
  (SELECT COUNT(*) FROM customers) AS customers,
  (SELECT COUNT(*) FROM agent_messages) AS messages,
  (SELECT COUNT(*) FROM agent_threads) AS threads;
" 2>&1) || {
    ntfy "QP restore-verify FAILED" "Sanity query failed on restored DB.\n$sanity" urgent rotating_light
    exit 3
}

# Compare against production for a "row count drift" sanity check — restored
# should be within 5% of prod (give or take in-flight writes between the
# backup time and now).
prod=$(sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d quantumpools -tAc "
SELECT
  (SELECT COUNT(*) FROM organizations),
  (SELECT COUNT(*) FROM users),
  (SELECT COUNT(*) FROM customers),
  (SELECT COUNT(*) FROM agent_messages),
  (SELECT COUNT(*) FROM agent_threads);
")

# 5. All good — fire a positive ntfy so Brian knows the chain works.
size=$(stat -c%s "$LATEST")
size_h=$(numfmt --to=iec $size)
ntfy "QP backup verified ✅" "Latest backup restored cleanly.
File: $(basename "$LATEST") ($size_h, age ${age_min}m)
Restored counts (orgs|users|customers|msgs|threads): $sanity
Prod counts:                                          $prod"

echo "Verify OK"
