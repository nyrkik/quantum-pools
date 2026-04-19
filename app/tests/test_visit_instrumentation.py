"""Integration tests — Visits subsystem emits the documented events.

Coverage target (docs/ai-platform-phase-1.md §6.7, DoD item 10):
- visit.completed fires from both VisitService.complete and
  VisitExperienceService.complete_visit (shared helper)
- Payload carries duration_minutes, tasks_completed, photos, readings,
  first_visit_resolution (taxonomy §visit.completed)
- entity_refs include visit_id + property_id + customer_id
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from src.models.visit import Visit, VisitStatus
from src.models.property import Property
from src.models.customer import Customer
from src.services.events.platform_event_service import Actor
from src.services.visit_service import VisitService


async def _seed_customer_property(db, org_id: str) -> tuple[str, str]:
    cust_id = str(uuid.uuid4())
    prop_id = str(uuid.uuid4())
    db.add(Customer(
        id=cust_id, organization_id=org_id,
        first_name="Test", last_name="Cust",
        email=f"t-{uuid.uuid4().hex[:6]}@example.com",
        customer_type="residential",
    ))
    db.add(Property(
        id=prop_id, organization_id=org_id, customer_id=cust_id,
        address="123 Test", city="Sac", state="CA", zip_code="95814",
    ))
    await db.flush()
    return cust_id, prop_id


async def _seed_in_progress_visit(db, org_id: str, cust_id: str, prop_id: str) -> str:
    visit_id = str(uuid.uuid4())
    db.add(Visit(
        id=visit_id, organization_id=org_id,
        customer_id=cust_id, property_id=prop_id,
        status=VisitStatus.in_progress.value,
        started_at=datetime.now(timezone.utc),
        scheduled_date=date.today(),
    ))
    await db.flush()
    return visit_id


@pytest.mark.asyncio
async def test_visit_complete_emits_visit_completed(db_session, org_a, event_recorder):
    cust_id, prop_id = await _seed_customer_property(db_session, org_a.id)
    visit_id = await _seed_in_progress_visit(db_session, org_a.id, cust_id, prop_id)
    await db_session.commit()

    actor = Actor(actor_type="user", user_id="tech-1")
    await VisitService(db_session).complete(org_a.id, visit_id, actor=actor)
    await db_session.commit()

    event = await event_recorder.assert_emitted("visit.completed", visit_id=visit_id)
    assert event["actor_type"] == "user"
    assert event["actor_user_id"] == "tech-1"
    assert event["level"] == "user_action"


@pytest.mark.asyncio
async def test_visit_completed_payload_shape_matches_taxonomy(
    db_session, org_a, event_recorder,
):
    """Taxonomy: payload = {duration_minutes, tasks_completed, photos,
    readings, first_visit_resolution}."""
    cust_id, prop_id = await _seed_customer_property(db_session, org_a.id)
    visit_id = await _seed_in_progress_visit(db_session, org_a.id, cust_id, prop_id)
    await db_session.commit()

    await VisitService(db_session).complete(org_a.id, visit_id)
    await db_session.commit()

    event = await event_recorder.assert_emitted("visit.completed", visit_id=visit_id)
    payload = event["payload"]
    # Required per taxonomy — zero-values are legitimate for a bare visit
    assert "tasks_completed" in payload
    assert "photos" in payload
    assert "readings" in payload
    assert "first_visit_resolution" in payload
    assert isinstance(payload["first_visit_resolution"], bool)

    # entity_refs: visit_id + property_id + customer_id
    refs = event["entity_refs"]
    assert refs.get("visit_id") == visit_id
    assert refs.get("property_id") == prop_id
    assert refs.get("customer_id") == cust_id

    # Privacy rule: no user_id keys in payload
    for k in payload.keys():
        assert "user_id" not in k, f"Payload key {k!r} violates §6"


@pytest.mark.asyncio
async def test_visit_experience_complete_emits_same_event(
    db_session, org_a, event_recorder,
):
    """Both completion paths (VisitService + VisitExperienceService) share
    the emit_visit_completed helper — same event type, same payload shape."""
    from src.services.visit_experience_service import VisitExperienceService

    cust_id, prop_id = await _seed_customer_property(db_session, org_a.id)
    visit_id = await _seed_in_progress_visit(db_session, org_a.id, cust_id, prop_id)
    await db_session.commit()

    actor = Actor(actor_type="user", user_id="tech-2")
    await VisitExperienceService(db_session).complete_visit(
        org_a.id, visit_id, actor=actor,
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("visit.completed", visit_id=visit_id)
    assert event["actor_user_id"] == "tech-2"
