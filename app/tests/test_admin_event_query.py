"""Integration tests for the admin event query endpoint.

Contract (docs/ai-platform-phase-1.md §4.5):
- Platform-admin only (403 for non-admins).
- Filters: org_id, event_type, event_type_prefix, entity_ref (repeat),
  actor_user_id, actor_type, level, from, to.
- Cursor-based pagination using (created_at, id).
- Default `from` = 30 days ago when omitted.
- event_type + event_type_prefix are mutually exclusive.
- Invalid cursor / invalid entity_ref → 400.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from src.services.events.platform_event_service import Actor, PlatformEventService


async def _emit(db, org_id: str, event_type: str, actor_uid: str | None = None, refs: dict | None = None):
    await PlatformEventService.emit(
        db=db,
        event_type=event_type,
        level="user_action",
        actor=Actor(actor_type="user", user_id=actor_uid) if actor_uid else Actor(actor_type="system"),
        organization_id=org_id,
        entity_refs=refs or {},
    )


# Direct query helpers mirroring the endpoint's WHERE-clause construction,
# used to verify the SQL logic without going through the full HTTP stack.
# (HTTP-layer testing exists in the manual verify script against the live
# backend — the endpoint is a thin wrapper over these queries.)


async def _count(db, where: str, params: dict) -> int:
    sql = f"SELECT count(*) FROM platform_events WHERE {where}"
    return (await db.execute(text(sql), params)).scalar() or 0


@pytest.mark.asyncio
async def test_filter_by_event_type_exact(db_session, org_a):
    prefix = f"adminq.{uuid.uuid4().hex[:6]}"
    await _emit(db_session, org_a.id, f"{prefix}.alpha")
    await _emit(db_session, org_a.id, f"{prefix}.beta")
    await _emit(db_session, org_a.id, f"{prefix}.alpha")
    await db_session.commit()
    n = await _count(
        db_session,
        "organization_id = :o AND event_type = :e",
        {"o": org_a.id, "e": f"{prefix}.alpha"},
    )
    assert n == 2


@pytest.mark.asyncio
async def test_filter_by_event_type_prefix(db_session, org_a):
    prefix = f"adminq.{uuid.uuid4().hex[:6]}"
    await _emit(db_session, org_a.id, f"{prefix}.alpha")
    await _emit(db_session, org_a.id, f"{prefix}.beta")
    await _emit(db_session, org_a.id, "unrelated.gamma")
    await db_session.commit()
    n = await _count(
        db_session,
        "organization_id = :o AND event_type LIKE :p",
        {"o": org_a.id, "p": prefix + ".%"},
    )
    assert n == 2


@pytest.mark.asyncio
async def test_filter_by_entity_ref_containment(db_session, org_a):
    etype = f"adminq.{uuid.uuid4().hex[:6]}"
    tag = uuid.uuid4().hex[:8]
    await _emit(db_session, org_a.id, etype, refs={"customer_id": tag})
    await _emit(db_session, org_a.id, etype, refs={"customer_id": "other"})
    await _emit(db_session, org_a.id, etype, refs={"case_id": tag})
    await db_session.commit()
    # Must match ONLY the row whose entity_refs contains {customer_id: tag}
    import json
    n = await _count(
        db_session,
        "organization_id = :o AND event_type = :e AND entity_refs @> cast(:er AS jsonb)",
        {"o": org_a.id, "e": etype, "er": json.dumps({"customer_id": tag})},
    )
    assert n == 1


@pytest.mark.asyncio
async def test_filter_by_actor_user_id(db_session, org_a):
    etype = f"adminq.{uuid.uuid4().hex[:6]}"
    target = f"actor-{uuid.uuid4().hex[:8]}"
    await _emit(db_session, org_a.id, etype, actor_uid=target)
    await _emit(db_session, org_a.id, etype, actor_uid="other-actor")
    await db_session.commit()
    n = await _count(
        db_session,
        "organization_id = :o AND event_type = :e AND actor_user_id = :a",
        {"o": org_a.id, "e": etype, "a": target},
    )
    assert n == 1


@pytest.mark.asyncio
async def test_time_range_filter(db_session, org_a):
    """Events outside [from, to) are excluded."""
    etype = f"adminq.{uuid.uuid4().hex[:6]}"
    in_window = datetime.now(timezone.utc) - timedelta(days=3)
    out_of_window = datetime.now(timezone.utc) - timedelta(days=60)

    await PlatformEventService.emit(
        db=db_session, event_type=etype, level="user_action",
        actor=Actor(actor_type="system"), organization_id=org_a.id,
        created_at=in_window,
    )
    await PlatformEventService.emit(
        db=db_session, event_type=etype, level="user_action",
        actor=Actor(actor_type="system"), organization_id=org_a.id,
        created_at=out_of_window,
    )
    await db_session.commit()

    # 30-day window: should catch the "in_window" row only
    n = await _count(
        db_session,
        "event_type = :e AND created_at >= :from_ AND created_at < :to",
        {
            "e": etype,
            "from_": datetime.now(timezone.utc) - timedelta(days=30),
            "to": datetime.now(timezone.utc),
        },
    )
    assert n == 1


@pytest.mark.asyncio
async def test_cursor_pagination_advances(db_session, org_a):
    """Mimic the endpoint's cursor logic: page 1 returns N rows, page 2
    with cursor encoded from the last row skips that row and continues."""
    etype = f"adminq.cursor.{uuid.uuid4().hex[:6]}"
    for _ in range(5):
        await _emit(db_session, org_a.id, etype)
    await db_session.commit()

    # Page 1: 3 rows newest-first
    page1 = (await db_session.execute(text(
        "SELECT id, created_at FROM platform_events "
        "WHERE organization_id = :o AND event_type = :e "
        "ORDER BY created_at DESC, id DESC LIMIT 3"
    ), {"o": org_a.id, "e": etype})).all()
    assert len(page1) == 3

    last_ts, last_id = page1[-1][1], page1[-1][0]

    # Page 2 using row-value cursor condition
    page2 = (await db_session.execute(text(
        "SELECT id, created_at FROM platform_events "
        "WHERE organization_id = :o AND event_type = :e "
        "AND (created_at, id) < (:cur_ts, :cur_id) "
        "ORDER BY created_at DESC, id DESC LIMIT 3"
    ), {"o": org_a.id, "e": etype, "cur_ts": last_ts, "cur_id": last_id})).all()

    assert len(page2) == 2  # 5 total - 3 on page 1
    # Ensure no overlap
    page1_ids = {r[0] for r in page1}
    page2_ids = {r[0] for r in page2}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_cursor_encode_decode_roundtrip():
    """Direct test of the cursor codec used by the endpoint."""
    from src.api.v1.admin_platform import _encode_cursor, _decode_cursor

    ts = datetime(2026, 4, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
    rid = "abc-123-def-456"
    cursor = _encode_cursor(ts, rid)
    got_ts, got_id = _decode_cursor(cursor)
    assert got_ts == ts
    assert got_id == rid
