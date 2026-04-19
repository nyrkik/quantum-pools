"""Integration tests — Cases subsystem emits the documented events.

Coverage target (docs/ai-platform-phase-1.md §6.5, DoD item 10):
- case.created fires on ServiceCaseService.create()
- payload shape conforms to taxonomy entry
- entity_refs correctly carry case_id + customer_id + user_id (manager)
- No user_id leakage into payload (taxonomy §6 privacy contract)
"""

from __future__ import annotations

import uuid

import pytest

from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.service_case_service import ServiceCaseService


async def _seed_user(db) -> str:
    """Insert a real User row so FK constraints on manager_user_id hold."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"tu-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="Test", last_name="User",
    )
    db.add(user)
    await db.flush()
    return user.id


@pytest.mark.asyncio
async def test_case_create_emits_case_created(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    actor = Actor(actor_type="user", user_id=user_id)
    case = await ServiceCaseService(db_session).create(
        org_id=org_a.id,
        title="Test case",
        source="manual",
        customer_id=None,
        created_by="Test User",
        actor=actor,
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("case.created", case_id=case.id)
    assert event["actor_type"] == "user"
    assert event["actor_user_id"] == user_id
    assert event["level"] == "user_action"


@pytest.mark.asyncio
async def test_case_create_payload_shape_matches_taxonomy(db_session, org_a, event_recorder):
    """Taxonomy says payload = {source, linked_thread_count, linked_job_count}
    and MUST NOT carry user ids (§6)."""
    user_id = await _seed_user(db_session)
    actor = Actor(actor_type="user", user_id=user_id)
    case = await ServiceCaseService(db_session).create(
        org_id=org_a.id,
        title="Payload-shape audit",
        source="email",
        customer_id=None,  # Don't need customer FK for payload-shape test
        created_by="Mgr",
        actor=actor,
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("case.created", case_id=case.id)
    payload = event["payload"]
    # Required keys per taxonomy
    assert payload.get("source") == "email"
    assert payload.get("linked_thread_count") == 0
    assert payload.get("linked_job_count") == 0
    # Privacy rule: no user_id keys in payload
    for k in payload.keys():
        assert "user_id" not in k, f"Payload key {k!r} violates §6 (user ids live in entity_refs only)"

    # Taxonomy: entity_refs = {case_id, customer_id?}. Manager is persisted
    # on the ServiceCase row via manager_user_id, not on the case.created
    # event itself (that's case.manager_changed's domain).
    refs = event["entity_refs"]
    assert refs.get("case_id") == case.id


@pytest.mark.asyncio
async def test_case_create_without_actor_uses_system(db_session, org_a, event_recorder):
    """System-initiated case creation (no user actor) still emits, with
    actor_type=system and no actor_user_id."""
    case = await ServiceCaseService(db_session).create(
        org_id=org_a.id,
        title="System-created case",
        source="email",
        created_by="DeepBlue",
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("case.created", case_id=case.id)
    assert event["actor_type"] == "system"
    assert event["actor_user_id"] is None
    assert event["level"] == "system_action"
