"""Daily retention purge for `platform_events`.

For each organization, deletes `platform_events` rows older than that
org's `event_retention_days`. Platform-level events (organization_id
IS NULL) are kept under a conservative default so meta-events (partition
creation, retention purge itself, etc.) aren't auto-expired alongside
org data.

Design notes:

* v1 is row-level DELETE. A per-partition DROP would be cleaner but
  requires org-specific partitioning, which v1 doesn't do.
* Batched DELETEs keep each transaction small — deleting 10M rows in
  one statement would lock the table for minutes.
* The purge itself is silent in the event stream; only the per-run
  summary `system.retention_purge.completed` is emitted. Emitting a
  row for every deletion would be self-cannibalizing.
* Guardrail: refuse to delete more than `SAFETY_MAX_PCT` of any single
  org's events in one run, and alert instead. Protects against a
  misconfigured `event_retention_days=1` nuking history.

See `docs/ai-platform-phase-1.md` §4.3.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization import Organization
from src.services.events.platform_event_service import (
    PlatformEventService,
    actor_system,
)

logger = logging.getLogger(__name__)

# Platform-level events (organization_id IS NULL) — e.g., login_failed,
# system.* meta-events. Retained for a long floor regardless of any
# per-org setting.
PLATFORM_DEFAULT_RETENTION_DAYS = 365 * 10  # 10 years

# Batch size per DELETE to keep locks short.
BATCH_SIZE = 50_000

# Safety cap: if a single run would delete more than this fraction of
# an org's rows, skip and alert instead. Catches misconfiguration.
SAFETY_MAX_PCT = 0.50


@dataclass
class OrgPurgeResult:
    organization_id: str
    retention_days: int
    rows_deleted: int = 0
    skipped_reason: Optional[str] = None  # "safety_cap" | "no_rows" | None


@dataclass
class PurgeReport:
    orgs_processed: int = 0
    rows_purged_total: int = 0
    platform_rows_purged: int = 0
    duration_ms: int = 0
    per_org: list[OrgPurgeResult] = field(default_factory=list)


async def _purge_one_org(
    db: AsyncSession, org_id: str, retention_days: int,
) -> OrgPurgeResult:
    result = OrgPurgeResult(organization_id=org_id, retention_days=retention_days)

    # Candidate count, for the safety check.
    total = (await db.execute(
        text("SELECT count(*) FROM platform_events WHERE organization_id = :o"),
        {"o": org_id},
    )).scalar() or 0
    if total == 0:
        result.skipped_reason = "no_rows"
        return result

    candidate = (await db.execute(
        text(
            "SELECT count(*) FROM platform_events "
            "WHERE organization_id = :o "
            "AND created_at < NOW() - make_interval(days => :d)"
        ),
        {"o": org_id, "d": retention_days},
    )).scalar() or 0
    if candidate == 0:
        result.skipped_reason = "no_rows"
        return result

    # Safety cap — refuse runs that would wipe too much at once.
    if candidate / total > SAFETY_MAX_PCT:
        logger.warning(
            "retention_purge safety cap hit for org %s: would delete %d/%d (%.1f%%); skipping",
            org_id, candidate, total, 100 * candidate / total,
        )
        result.skipped_reason = "safety_cap"
        return result

    # Batched delete. ctid-based batching keeps the DELETE fast on a
    # partitioned table without needing a UUID range scan.
    deleted_total = 0
    while True:
        res = await db.execute(
            text(
                "DELETE FROM platform_events "
                "WHERE ctid IN ("
                "  SELECT ctid FROM platform_events "
                "  WHERE organization_id = :o "
                "  AND created_at < NOW() - make_interval(days => :d) "
                "  LIMIT :n"
                ")"
            ),
            {"o": org_id, "d": retention_days, "n": BATCH_SIZE},
        )
        await db.commit()
        deleted = res.rowcount or 0
        deleted_total += deleted
        if deleted < BATCH_SIZE:
            break

    result.rows_deleted = deleted_total
    return result


async def _purge_platform_events(db: AsyncSession) -> int:
    """Purge platform-level events (org_id IS NULL) past the long-floor."""
    res = await db.execute(
        text(
            "DELETE FROM platform_events "
            "WHERE organization_id IS NULL "
            "AND created_at < NOW() - make_interval(days => :d)"
        ),
        {"d": PLATFORM_DEFAULT_RETENTION_DAYS},
    )
    await db.commit()
    return res.rowcount or 0


async def purge_expired_events(db: AsyncSession) -> PurgeReport:
    """APScheduler entry point.

    Iterates every org, deletes platform_events older than the org's
    retention setting. Emits a single summary meta-event at the end.
    """
    t0 = time.monotonic()
    report = PurgeReport()

    orgs = (await db.execute(select(Organization))).scalars().all()
    for org in orgs:
        retention = org.event_retention_days or PLATFORM_DEFAULT_RETENTION_DAYS
        try:
            r = await _purge_one_org(db, org.id, retention)
        except Exception as e:  # noqa: BLE001 — per-org failure mustn't break the loop
            logger.error("retention_purge failed for org %s: %s", org.id, e)
            r = OrgPurgeResult(
                organization_id=org.id, retention_days=retention,
                skipped_reason=f"error:{type(e).__name__}",
            )
        report.per_org.append(r)
        report.orgs_processed += 1
        report.rows_purged_total += r.rows_deleted

    try:
        report.platform_rows_purged = await _purge_platform_events(db)
    except Exception as e:  # noqa: BLE001
        logger.error("retention_purge platform-level pass failed: %s", e)

    report.duration_ms = int((time.monotonic() - t0) * 1000)

    await PlatformEventService.emit(
        db=db,
        event_type="system.retention_purge.completed",
        level="system_action",
        actor=actor_system(),
        organization_id=None,
        payload={
            "orgs_processed": report.orgs_processed,
            "rows_purged_total": report.rows_purged_total + report.platform_rows_purged,
            "platform_rows_purged": report.platform_rows_purged,
            "duration_ms": report.duration_ms,
        },
    )
    await db.commit()

    logger.info(
        "retention_purge complete: orgs=%d rows=%d platform_rows=%d duration_ms=%d",
        report.orgs_processed, report.rows_purged_total,
        report.platform_rows_purged, report.duration_ms,
    )
    return report
