"""Monthly partition management for `platform_events`.

APScheduler runs `ensure_next_partition()` on the 25th of every month
(see `app.py`). Creating the partition ahead of month-end is critical:
the day a partition is missing, INSERTs into `platform_events` start
failing — fail-soft at the emit layer means the event silently never
lands, and we'd lose observability for the first events of the new
month.

Postgres propagates indexes from the parent partitioned table to each
new partition automatically, so `CREATE TABLE ... PARTITION OF` is
enough — no separate index creation needed.

See `docs/ai-platform-phase-1.md` §4.2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import (
    PlatformEventService,
    actor_system,
)

logger = logging.getLogger(__name__)


@dataclass
class PartitionPlan:
    """Month-range partition descriptor. All three fields are derived
    from the same anchor date, but callers may want them separately for
    logging and the emitted meta-event payload."""

    partition_name: str        # platform_events_YYYY_MM
    range_start: date          # inclusive lower bound (YYYY-MM-01)
    range_end: date            # exclusive upper bound (first of next month)


def _plan_for_month(year: int, month: int) -> PartitionPlan:
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    return PartitionPlan(
        partition_name=f"platform_events_{year:04d}_{month:02d}",
        range_start=date(year, month, 1),
        range_end=date(next_year, next_month, 1),
    )


def plan_next_month(now: datetime | None = None) -> PartitionPlan:
    """The partition covering the month AFTER `now`.

    Called from the 25th-of-month cron, so this always resolves to the
    upcoming month's partition.
    """
    now = now or datetime.now(timezone.utc)
    if now.month == 12:
        return _plan_for_month(now.year + 1, 1)
    return _plan_for_month(now.year, now.month + 1)


async def ensure_partition(db: AsyncSession, plan: PartitionPlan) -> bool:
    """Create the partition if it doesn't already exist.

    Returns True when a partition was created, False when it already
    existed. Idempotent: re-running on the same day is a no-op.
    """
    # `CREATE TABLE IF NOT EXISTS ... PARTITION OF` lets us retry without
    # checking first — the statement itself is the check.
    # Partition-name values are derived from `date(year, month, 1)` so
    # they're safe to interpolate; we still use text()+format because
    # PARTITION OF DDL can't be fully parameterized.
    sql = (
        f"CREATE TABLE IF NOT EXISTS {plan.partition_name} "
        f"PARTITION OF platform_events "
        f"FOR VALUES FROM ('{plan.range_start.isoformat()}') "
        f"TO ('{plan.range_end.isoformat()}')"
    )
    # Detect whether the partition existed before we touched it so the
    # emitted event differentiates "created" vs "already existed".
    existed_before = (await db.execute(
        text("SELECT 1 FROM pg_class WHERE relname = :n AND relkind = 'r'"),
        {"n": plan.partition_name},
    )).first() is not None

    await db.execute(text(sql))
    await db.commit()
    return not existed_before


async def ensure_next_partition(db: AsyncSession) -> PartitionPlan:
    """APScheduler entry point.

    Wraps `ensure_partition(plan_next_month())` with the `system.partition.created`
    meta-event when a new partition was made. The event is platform-scoped
    (`organization_id=None`) so it shows up regardless of org.
    """
    plan = plan_next_month()
    logger.info(
        "platform_events partition check: %s (range %s → %s)",
        plan.partition_name, plan.range_start, plan.range_end,
    )
    created = await ensure_partition(db, plan)

    if created:
        await PlatformEventService.emit(
            db=db,
            event_type="system.partition.created",
            level="system_action",
            actor=actor_system(),
            organization_id=None,
            payload={
                "partition_name": plan.partition_name,
                "range_start": plan.range_start.isoformat(),
                "range_end": plan.range_end.isoformat(),
            },
        )
        await db.commit()
        logger.info("Created partition %s", plan.partition_name)
    else:
        logger.info("Partition %s already existed", plan.partition_name)

    return plan
