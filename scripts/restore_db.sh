#!/bin/bash
# RESTORE — emergency use only. Streams a gzipped pg_dump into the live
# database, OVERWRITING current data. There is no undo.
#
# Usage:
#   ./restore_db.sh <backup_file.sql.gz>
#
# Safety:
#   - Refuses to run without explicit --yes flag
#   - Takes a fresh snapshot of current state first (so you can roll back the
#     restore if it was the wrong file)
#   - Drops and recreates the target DB

set -euo pipefail

if [ "$#" -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    cat <<EOF
Usage: $0 <backup_file.sql.gz> --yes [--db <name>]

OVERWRITES the target database. There is no undo. A pre-restore snapshot is
saved to /srv/quantumpools/backups/pre_restore_<timestamp>.sql.gz first.

Example:
  $0 /srv/quantumpools/backups/quantumpools_20260413_030000.sql.gz --yes
EOF
    exit 1
fi

BACKUP_FILE="$1"
shift
TARGET_DB="quantumpools"
CONFIRMED=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes) CONFIRMED=1; shift ;;
        --db) TARGET_DB="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

if [ "$CONFIRMED" -ne 1 ]; then
    echo "Refusing to restore without --yes flag (this OVERWRITES $TARGET_DB)."
    exit 1
fi

DB_CONTAINER="quantumpools-db"
DB_USER="quantumpools"

# 1. Snapshot current state first.
TS=$(date -u +%Y%m%d_%H%M%S)
PRE_SNAP="/srv/quantumpools/backups/pre_restore_${TS}.sql.gz"
echo "Snapshotting current $TARGET_DB to $PRE_SNAP ..."
sudo docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$TARGET_DB" --no-owner --no-acl | gzip > "$PRE_SNAP"
echo "Pre-restore snapshot: $PRE_SNAP ($(numfmt --to=iec $(stat -c%s "$PRE_SNAP")))"

# 2. Stop services that might write during restore.
echo "Stopping backend + agent services..."
sudo systemctl stop quantumpools-backend quantumpools-agent

# 3. Drop+recreate target.
echo "Dropping and recreating $TARGET_DB..."
sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $TARGET_DB;"
sudo docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $TARGET_DB OWNER $DB_USER;"

# 4. Restore.
echo "Restoring from $BACKUP_FILE..."
gunzip -c "$BACKUP_FILE" | sudo docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$TARGET_DB" >/tmp/qp_restore.log 2>&1 || {
    echo "RESTORE FAILED. See /tmp/qp_restore.log"
    echo "Pre-restore snapshot is at $PRE_SNAP — restore that to recover."
    exit 2
}

# 5. Restart services.
echo "Restarting services..."
sudo systemctl start quantumpools-backend quantumpools-agent

echo "Restore complete. Pre-restore snapshot retained at $PRE_SNAP for rollback."
