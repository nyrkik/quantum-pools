#!/bin/bash
# QuantumPools nightly DB backup.
# Runs pg_dump from inside the Postgres container, gzips, writes to
# /srv/quantumpools/backups/ with a date-stamped filename. ntfy alert on
# failure (silent on success — see weekly verification for proof of life).
#
# GFS retention applied here:
#   - Last 7 daily backups kept
#   - Daily older than 7 days but newer than 28 → kept only if Sunday (weekly)
#   - Weekly older than 28 days → kept only if 1st of month (monthly)
#   - Monthly older than 365 days → deleted
#
# Restore: see scripts/restore_db.sh
# Verification: scripts/verify_backup.sh runs every Sunday at 4am

set -euo pipefail

BACKUP_DIR="/srv/quantumpools/backups"
DB_CONTAINER="quantumpools-db"
DB_USER="quantumpools"
DB_NAME="quantumpools"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUTFILE="${BACKUP_DIR}/quantumpools_${TIMESTAMP}.sql.gz"
NTFY_URL="${NTFY_URL:-http://localhost:7031}"
NTFY_TOPIC="${NTFY_TOPIC:-qp-alerts}"

mkdir -p "$BACKUP_DIR"

ntfy_alert() {
    local title="$1"
    local body="$2"
    curl -s -H "Title: $title" -H "Priority: high" -H "Tags: warning" \
         -d "$body" "${NTFY_URL}/${NTFY_TOPIC}" >/dev/null 2>&1 || true
}

# 1. Dump
if ! sudo docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl 2>/tmp/qp_backup_err | gzip > "$OUTFILE"; then
    err=$(cat /tmp/qp_backup_err 2>/dev/null | tail -5)
    ntfy_alert "QP backup FAILED" "pg_dump failed at ${TIMESTAMP}.\nError: ${err}"
    exit 1
fi

# Sanity check: file should be at least a few KB (an empty/failed dump is tiny)
size=$(stat -c%s "$OUTFILE")
if [ "$size" -lt 5000 ]; then
    ntfy_alert "QP backup SUSPICIOUS" "Backup ${OUTFILE} is only ${size} bytes — likely incomplete."
    exit 2
fi

# 2. Retention — GFS scheme
DOW=$(date -u +%u)   # 1-7, Mon=1, Sun=7
DOM=$(date -u +%d)   # 01-31

# Loop through all backup files older than 7 days
find "$BACKUP_DIR" -name 'quantumpools_*.sql.gz' -type f -mtime +7 | while read -r f; do
    # Extract date from filename: quantumpools_YYYYMMDD_HHMMSS.sql.gz
    fname=$(basename "$f")
    date_part=$(echo "$fname" | sed -E 's/^quantumpools_([0-9]{8})_.*$/\1/')
    if ! [[ "$date_part" =~ ^[0-9]{8}$ ]]; then
        continue  # not our format, skip
    fi
    file_dow=$(date -d "${date_part:0:4}-${date_part:4:2}-${date_part:6:2}" +%u)
    file_dom=${date_part:6:2}

    age_days=$(( ($(date +%s) - $(date -d "${date_part:0:4}-${date_part:4:2}-${date_part:6:2}" +%s)) / 86400 ))

    if [ "$age_days" -le 28 ]; then
        # 8-28 days old: keep only Sundays (file_dow == 7)
        if [ "$file_dow" -ne 7 ]; then
            rm -f "$f"
        fi
    elif [ "$age_days" -le 365 ]; then
        # 28-365 days: keep only 1st of month
        if [ "$file_dom" != "01" ]; then
            rm -f "$f"
        fi
    else
        # >365 days: delete
        rm -f "$f"
    fi
done

# Silent on success — the absence of nightly ntfy is itself the signal.
# (The weekly verify_backup.sh fires a positive ntfy so we know it's alive.)
echo "Backup OK: ${OUTFILE} ($(numfmt --to=iec $size))"
