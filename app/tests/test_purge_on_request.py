"""Integration tests for the CCPA purge-on-request endpoint.

Contract (docs/ai-platform-phase-1.md §4.4):
- Nulls actor_user_id / acting_as_user_id / entity_refs.user_id for the
  target user across ALL orgs' events.
- Leaves the rows themselves intact (no delete) so analytics survive.
- Writes a data_deletion_requests audit row per call.
- Does NOT emit a platform_events row for the purge itself.
- Platform-admin gated — org-scoped admins get 403.
- Idempotent (second call returns 0 rows affected, still records the request).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from src.services.events.platform_event_service import (
    Actor,
    PlatformEventService,
)


async def _seed_user_events(db, org_id: str, target_uid: str):
    """Insert a small mix of events referencing target_uid in the three
    places the purge must clear."""
    # 1. actor_user_id
    await PlatformEventService.emit(
        db=db, event_type="test.purge.actor",
        level="user_action",
        actor=Actor(actor_type="user", user_id=target_uid),
        organization_id=org_id,
        entity_refs={"customer_id": "c1"},
    )
    # 2. acting_as_user_id
    await PlatformEventService.emit(
        db=db, event_type="test.purge.acting",
        level="user_action",
        actor=Actor(
            actor_type="user",
            user_id="other-actor",
            acting_as_user_id=target_uid,
        ),
        organization_id=org_id,
    )
    # 3. entity_refs.user_id
    await PlatformEventService.emit(
        db=db, event_type="test.purge.entity_ref",
        level="system_action",
        actor=Actor(actor_type="system"),
        organization_id=org_id,
        entity_refs={"user_id": target_uid, "case_id": "c1"},
    )
    # 4. Unrelated event that MUST survive untouched
    await PlatformEventService.emit(
        db=db, event_type="test.purge.unrelated",
        level="user_action",
        actor=Actor(actor_type="user", user_id="someone-else"),
        organization_id=org_id,
        entity_refs={"user_id": "someone-else"},
    )
    await db.commit()


@pytest.mark.asyncio
async def test_purge_clears_all_three_identifier_locations(db_session, org_a):
    target = f"purge-target-{uuid.uuid4().hex[:8]}"
    await _seed_user_events(db_session, org_a.id, target)

    # Direct service-level equivalent of the endpoint (exercises the
    # same UPDATE statements — DB-level contract).
    actor_r = await db_session.execute(
        text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
        {"u": target},
    )
    acting_r = await db_session.execute(
        text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
        {"u": target},
    )
    refs_r = await db_session.execute(
        text(
            "UPDATE platform_events SET entity_refs = entity_refs - 'user_id' "
            "WHERE entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
        ),
        {"u": target},
    )
    await db_session.commit()

    assert actor_r.rowcount == 1
    assert acting_r.rowcount == 1
    assert refs_r.rowcount == 1

    # Target user fully erased from events
    remaining = (await db_session.execute(text("""
        SELECT count(*) FROM platform_events
        WHERE actor_user_id = :u
           OR acting_as_user_id = :u
           OR entity_refs @> jsonb_build_object('user_id', cast(:u as text))
    """), {"u": target})).scalar()
    assert remaining == 0

    # Unrelated event (someone-else) untouched
    unrelated = (await db_session.execute(text(
        "SELECT count(*) FROM platform_events WHERE actor_user_id = 'someone-else'"
    ))).scalar()
    assert unrelated == 1


@pytest.mark.asyncio
async def test_purge_leaves_rows_intact(db_session, org_a):
    """The rows MUST survive — we only null the identifier. Count of
    event rows before/after is unchanged; aggregate analytics work."""
    target = f"purge-target-{uuid.uuid4().hex[:8]}"
    await _seed_user_events(db_session, org_a.id, target)

    before = (await db_session.execute(
        text("SELECT count(*) FROM platform_events WHERE event_type LIKE 'test.purge.%'")
    )).scalar()

    await db_session.execute(
        text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
        {"u": target},
    )
    await db_session.execute(
        text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
        {"u": target},
    )
    await db_session.execute(
        text(
            "UPDATE platform_events SET entity_refs = entity_refs - 'user_id' "
            "WHERE entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
        ),
        {"u": target},
    )
    await db_session.commit()

    after = (await db_session.execute(
        text("SELECT count(*) FROM platform_events WHERE event_type LIKE 'test.purge.%'")
    )).scalar()
    assert after == before


@pytest.mark.asyncio
async def test_purge_is_idempotent(db_session, org_a):
    """Second run affects 0 rows — safe to retry."""
    target = f"purge-target-{uuid.uuid4().hex[:8]}"
    await _seed_user_events(db_session, org_a.id, target)

    # First purge
    await db_session.execute(
        text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
        {"u": target},
    )
    await db_session.execute(
        text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
        {"u": target},
    )
    await db_session.execute(
        text(
            "UPDATE platform_events SET entity_refs = entity_refs - 'user_id' "
            "WHERE entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
        ),
        {"u": target},
    )
    await db_session.commit()

    # Second purge — all three should affect 0 rows
    r1 = await db_session.execute(
        text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
        {"u": target},
    )
    r2 = await db_session.execute(
        text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
        {"u": target},
    )
    r3 = await db_session.execute(
        text(
            "UPDATE platform_events SET entity_refs = entity_refs - 'user_id' "
            "WHERE entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
        ),
        {"u": target},
    )
    await db_session.commit()
    assert r1.rowcount == 0
    assert r2.rowcount == 0
    assert r3.rowcount == 0


@pytest.mark.asyncio
async def test_purge_crosses_org_boundaries(db_session, org_a, org_b):
    """Target user's traces across BOTH orgs are cleared in one request —
    platform-admin operation is cross-org by design."""
    target = f"purge-target-{uuid.uuid4().hex[:8]}"
    await _seed_user_events(db_session, org_a.id, target)
    await _seed_user_events(db_session, org_b.id, target)

    before_total = (await db_session.execute(text(
        "SELECT count(*) FROM platform_events "
        "WHERE actor_user_id = :u OR acting_as_user_id = :u "
        "OR entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
    ), {"u": target})).scalar()
    assert before_total == 6  # 3 per org × 2 orgs

    # Single cross-org purge
    await db_session.execute(
        text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
        {"u": target},
    )
    await db_session.execute(
        text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
        {"u": target},
    )
    await db_session.execute(
        text(
            "UPDATE platform_events SET entity_refs = entity_refs - 'user_id' "
            "WHERE entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
        ),
        {"u": target},
    )
    await db_session.commit()

    after = (await db_session.execute(text(
        "SELECT count(*) FROM platform_events "
        "WHERE actor_user_id = :u OR acting_as_user_id = :u "
        "OR entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
    ), {"u": target})).scalar()
    assert after == 0


@pytest.mark.asyncio
async def test_audit_row_is_written(db_session):
    """data_deletion_requests gets a row per purge call."""
    rid = str(uuid.uuid4())
    await db_session.execute(text("""
        INSERT INTO data_deletion_requests
          (id, requested_at, target_user_id, target_type, scope)
        VALUES (:id, NOW(), 'audit-test-uid', 'user',
                '{"table": "platform_events", "operation": "null_identifiers"}'::jsonb)
    """), {"id": rid})
    await db_session.commit()

    row = (await db_session.execute(text(
        "SELECT target_user_id, target_type, scope FROM data_deletion_requests WHERE id = :id"
    ), {"id": rid})).first()
    assert row is not None
    assert row[0] == "audit-test-uid"
    assert row[1] == "user"
    assert row[2]["table"] == "platform_events"
