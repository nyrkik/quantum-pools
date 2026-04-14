# Database Backup & Restore Runbook

> Built 2026-04-13 in response to the inbox security audit operational gap "no backup verification." Source of truth for everything backup-related.

## What's running

| Job | Schedule | Script | Log |
|---|---|---|---|
| Nightly backup | 3:00 UTC daily | `scripts/backup_db.sh` | `/var/log/qp-backup.log` |
| Restore verification | 4:00 UTC Sunday | `scripts/verify_backup.sh` | `/var/log/qp-backup-verify.log` |

Cron entries live in Brian's user crontab (`crontab -l`).

## Where backups live

`/srv/quantumpools/backups/` on the MS-01 host. Filenames follow `quantumpools_YYYYMMDD_HHMMSS.sql.gz` (UTC). Pre-restore safety snapshots use `pre_restore_<timestamp>.sql.gz`. One-off pre-migration snapshots from earlier sessions also live here with descriptive prefixes (e.g. `inspection_pre_walker_*.sql`).

DB is currently ~39 MB compressed → ~2.5 MB. Storage cost is trivial.

## Retention policy (GFS — Grandfather/Father/Son)

`backup_db.sh` enforces this every night after the dump:

| Age | Kept |
|---|---|
| 0-7 days | All daily backups |
| 8-28 days | Sundays only (weekly) |
| 29-365 days | 1st of month only (monthly) |
| >365 days | Deleted |

So at steady state we hold ~7 daily + ~3 weekly + ~12 monthly = ~22 backups.

## Restore — when something has gone very wrong

```bash
# 1. Pick a backup (most recent first)
ls -lt /srv/quantumpools/backups/quantumpools_*.sql.gz | head -10

# 2. Restore it. This OVERWRITES the live database. The script:
#    - Snapshots current state to pre_restore_<timestamp>.sql.gz first (rollback path)
#    - Stops backend + agent services
#    - Drops + recreates `quantumpools` DB
#    - Restores from the chosen file
#    - Restarts services
/srv/quantumpools/scripts/restore_db.sh /srv/quantumpools/backups/quantumpools_20260413_030000.sql.gz --yes

# 3. If restore was wrong, roll back using the pre-restore snapshot:
/srv/quantumpools/scripts/restore_db.sh /srv/quantumpools/backups/pre_restore_<timestamp>.sql.gz --yes
```

The `--yes` flag is required — without it the script refuses to run.

## How we know backups actually work

The Sunday verify job:
1. Picks the most recent backup
2. Drops + creates a `quantumpools_restore_test` scratch DB inside the same Postgres container
3. Streams the backup into it
4. Runs sanity queries (organizations, users, customers, agent_messages, agent_threads row counts)
5. Compares restored counts against current production counts (drift should be tiny)
6. Drops the scratch DB
7. Fires a positive ntfy with the comparison

The positive ntfy ("QP backup verified ✅") is the proof of life. Absence of it on a Sunday means something's broken — go look at `/var/log/qp-backup-verify.log`.

## Failure signaling (ntfy)

Every script publishes to `qp-alerts` topic on the local ntfy (MS-01:7031):

| Event | Title | Priority |
|---|---|---|
| Backup script crashed | "QP backup FAILED" | high |
| Backup file suspiciously small (<5 KB) | "QP backup SUSPICIOUS" | high |
| Verify can't find any backups | "QP restore-verify FAILED" | high |
| Verify finds latest backup is >25h old | "QP backup STALE" | high |
| Verify restore fails | "QP restore-verify FAILED" | urgent |
| Sanity query on restored DB fails | "QP restore-verify FAILED" | urgent |
| Verify succeeds | "QP backup verified ✅" | default |

## What's NOT yet built (follow-ups)

- **Off-host backup**: `/mnt/nas` is referenced in CLAUDE.md but isn't currently mounted on this host. Once mounted, add `cp` or `rsync` to a NAS subdirectory at end of `backup_db.sh` so a fire/disk-failure on MS-01 doesn't lose everything.
- **Off-site backup**: nothing replicates beyond the LAN. If full off-site is needed (S3, B2, etc.), layer on top of the existing files in `/srv/quantumpools/backups/` — they're already gzipped + portable.
- **Continuous WAL archiving**: current setup gives us up to 24h of data loss if MS-01 dies between nightly runs. WAL archiving (point-in-time recovery) would close that to seconds. Not yet warranted given DB size + traffic, but worth considering once paying customers come on.

## Manual emergency backup (anytime)

```bash
/srv/quantumpools/scripts/backup_db.sh
```

That's idempotent — running it ad-hoc just adds another timestamped file. Useful before risky migrations or one-off data ops.
