"""Unit tests for platform_events partition manager.

Contract (docs/ai-platform-phase-1.md §4.2):
- plan_next_month returns next month's partition name + range.
- ensure_partition is idempotent (second call = no-op, no error).
- A new partition emits `system.partition.created` meta-event with
  null organization_id and the plan in payload.
- If the partition already existed, no event is emitted.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from src.services.events.partition_manager import (
    ensure_next_partition,
    ensure_partition,
    plan_next_month,
    _plan_for_month,
)


def test_plan_for_month_midyear():
    p = _plan_for_month(2026, 5)
    assert p.partition_name == "platform_events_2026_05"
    assert p.range_start == date(2026, 5, 1)
    assert p.range_end == date(2026, 6, 1)


def test_plan_for_month_december_rolls_year():
    p = _plan_for_month(2026, 12)
    assert p.partition_name == "platform_events_2026_12"
    assert p.range_start == date(2026, 12, 1)
    assert p.range_end == date(2027, 1, 1)


def test_plan_next_month_uses_current_month_plus_one():
    # Fixed anchor in August 2026 → September partition.
    anchor = datetime(2026, 8, 15, tzinfo=timezone.utc)
    p = plan_next_month(now=anchor)
    assert p.partition_name == "platform_events_2026_09"
    assert p.range_start == date(2026, 9, 1)
    assert p.range_end == date(2026, 10, 1)


def test_plan_next_month_december_rolls_year():
    anchor = datetime(2026, 12, 3, tzinfo=timezone.utc)
    p = plan_next_month(now=anchor)
    assert p.partition_name == "platform_events_2027_01"
    assert p.range_start == date(2027, 1, 1)


async def _parent_is_partitioned(db) -> bool:
    """Test DB builds schema via Base.metadata.create_all, which doesn't
    honor declarative partitioning — the table exists as a plain table
    there. Production has the parent as PARTITIONED BY RANGE (created_at)
    via Alembic. These DB-level tests only make sense against the
    production-shaped table; we skip otherwise so they don't block CI."""
    row = await db.execute(text(
        "SELECT c.relkind FROM pg_class c WHERE c.relname = 'platform_events'"
    ))
    rel = row.scalar()
    return rel == "p"  # 'p' = partitioned table


@pytest.mark.asyncio
async def test_ensure_partition_creates_and_is_idempotent(db_session):
    if not await _parent_is_partitioned(db_session):
        pytest.skip("platform_events is not partitioned in the test DB")

    plan = _plan_for_month(2099, 6)  # far future, guaranteed absent
    await db_session.execute(text(f"DROP TABLE IF EXISTS {plan.partition_name}"))
    await db_session.commit()

    created_first = await ensure_partition(db_session, plan)
    created_second = await ensure_partition(db_session, plan)

    assert created_first is True
    assert created_second is False  # idempotent

    await db_session.execute(text(f"DROP TABLE IF EXISTS {plan.partition_name}"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_ensure_next_partition_emits_meta_event(db_session):
    if not await _parent_is_partitioned(db_session):
        pytest.skip("platform_events is not partitioned in the test DB")

    plan = plan_next_month()
    await db_session.execute(text(f"DROP TABLE IF EXISTS {plan.partition_name}"))
    await db_session.commit()

    await ensure_next_partition(db_session)

    row = (await db_session.execute(text(
        "SELECT event_type, organization_id, payload "
        "FROM platform_events "
        "WHERE event_type = 'system.partition.created' "
        "ORDER BY created_at DESC LIMIT 1"
    ))).first()
    assert row is not None
    assert row[0] == "system.partition.created"
    assert row[1] is None
    assert row[2]["partition_name"] == plan.partition_name

    await ensure_next_partition(db_session)
    count = (await db_session.execute(text(
        "SELECT count(*) FROM platform_events "
        "WHERE event_type='system.partition.created' "
        "AND payload->>'partition_name' = :n"
    ), {"n": plan.partition_name})).scalar()
    assert count == 1

    await db_session.execute(text(f"DROP TABLE IF EXISTS {plan.partition_name}"))
    await db_session.commit()
