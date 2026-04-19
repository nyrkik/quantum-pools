"""Unit tests for platform_events retention purge.

Contract (docs/ai-platform-phase-1.md §4.3):
- Events older than org's event_retention_days are deleted.
- Events within the retention window survive.
- Per-org — org A's retention doesn't reach org B's events.
- Safety cap: if a run would delete >50% of an org's events, skip and log.
- One summary `system.retention_purge.completed` emitted per run.
- Platform-level events (org_id NULL) use the 10-year floor regardless.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text

from src.services.events.retention_purge import (
    PLATFORM_DEFAULT_RETENTION_DAYS,
    SAFETY_MAX_PCT,
    purge_expired_events,
    _purge_one_org,
)


async def _insert_event(db, org_id: str | None, age_days: int, event_type: str = "test.purge"):
    ts = datetime.now(timezone.utc) - timedelta(days=age_days)
    await db.execute(text("""
        INSERT INTO platform_events
          (id, organization_id, actor_type, event_type, level,
           entity_refs, payload, created_at)
        VALUES
          (:id, :org, 'system', :e, 'system_action',
           '{}'::jsonb, '{}'::jsonb, :ts)
    """), {"id": str(uuid.uuid4()), "org": org_id, "e": event_type, "ts": ts})


async def _count(db, org_id: str | None):
    return (await db.execute(
        text("SELECT count(*) FROM platform_events WHERE organization_id IS NOT DISTINCT FROM :o"),
        {"o": org_id},
    )).scalar() or 0


@pytest.mark.asyncio
async def test_purge_deletes_rows_older_than_retention(db_session, org_a):
    # Retention = 30 days on org_a.
    await db_session.execute(text(
        "UPDATE organizations SET event_retention_days = 30 WHERE id = :o"
    ), {"o": org_a.id})
    # 10 old rows + 10 fresh rows so old is 50% and NOT above the safety cap
    # (the cap triggers strictly greater-than).
    for _ in range(10):
        await _insert_event(db_session, org_a.id, age_days=60)
    for _ in range(10):
        await _insert_event(db_session, org_a.id, age_days=5)
    await db_session.commit()

    result = await _purge_one_org(db_session, org_a.id, retention_days=30)
    assert result.rows_deleted == 10
    assert result.skipped_reason is None
    remaining = await _count(db_session, org_a.id)
    assert remaining == 10


@pytest.mark.asyncio
async def test_purge_respects_per_org_isolation(db_session, org_a, org_b):
    # Both orgs have 30-day retention; only old rows in A should be deleted.
    await db_session.execute(text(
        "UPDATE organizations SET event_retention_days = 30 WHERE id IN (:a, :b)"
    ), {"a": org_a.id, "b": org_b.id})
    # org_a: 5 old + 20 fresh (old is 20% of total — under cap)
    for _ in range(5):
        await _insert_event(db_session, org_a.id, age_days=60)
    for _ in range(20):
        await _insert_event(db_session, org_a.id, age_days=5)
    # org_b: 5 recent only
    for _ in range(5):
        await _insert_event(db_session, org_b.id, age_days=10)
    await db_session.commit()

    await _purge_one_org(db_session, org_a.id, retention_days=30)
    # org_b untouched
    assert await _count(db_session, org_b.id) == 5
    # org_a lost only the 5 old
    assert await _count(db_session, org_a.id) == 20


@pytest.mark.asyncio
async def test_purge_safety_cap_blocks_mass_delete(db_session, org_a):
    # 10 rows all old: 100% would be deleted → safety cap triggers.
    for _ in range(10):
        await _insert_event(db_session, org_a.id, age_days=90)
    await db_session.commit()

    result = await _purge_one_org(db_session, org_a.id, retention_days=30)
    assert result.rows_deleted == 0
    assert result.skipped_reason == "safety_cap"
    assert await _count(db_session, org_a.id) == 10


@pytest.mark.asyncio
async def test_purge_expired_events_emits_summary(db_session, org_a):
    # Ensure Sapphire-style long retention so org_a doesn't get purged
    # (safety cap test above covers delete path).
    await db_session.execute(text(
        "UPDATE organizations SET event_retention_days = 3650 WHERE id = :o"
    ), {"o": org_a.id})
    await db_session.commit()

    before = (await db_session.execute(text(
        "SELECT count(*) FROM platform_events "
        "WHERE event_type='system.retention_purge.completed'"
    ))).scalar()

    await purge_expired_events(db_session)
    await db_session.commit()

    after = (await db_session.execute(text(
        "SELECT count(*) FROM platform_events "
        "WHERE event_type='system.retention_purge.completed'"
    ))).scalar()
    assert after == before + 1

    row = (await db_session.execute(text(
        "SELECT organization_id, payload FROM platform_events "
        "WHERE event_type='system.retention_purge.completed' "
        "ORDER BY created_at DESC LIMIT 1"
    ))).first()
    assert row[0] is None  # platform-scoped
    payload = row[1]
    assert "orgs_processed" in payload
    assert "rows_purged_total" in payload
    assert "duration_ms" in payload
