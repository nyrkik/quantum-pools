"""Integration test — inbox subsystem emits expected events.

First Phase-1-Step-4 integration test. Verifies end-to-end that calling
AgentThreadService methods lands correctly-shaped rows in platform_events
with the right entity_refs, actor, level, and payload.

Scenarios covered:
- archive_thread → `thread.archived` with prior_status in payload + correct actor
- assign_thread (assign + unassign) → `thread.assigned` with prior_assignee_id
- archive_thread called without actor → `system_action` level

Not covered yet (Step 5+): thread.opened via HTTP route (requires async
client fixture), inbound orchestrator's 3 AgentMessage creation sites,
classifier/matcher events.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.services.agent_thread_service import AgentThreadService
from src.services.events.actor_factory import actor_system
from src.services.events.platform_event_service import Actor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_thread(db_session, org_a):
    """Minimal thread seeded directly into the DB.

    We bypass the full orchestrator path — this test is about the instrumented
    state-change methods, not the classification pipeline.
    """
    thread_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            """
            INSERT INTO agent_threads
              (id, thread_key, contact_email, subject, organization_id,
               status, category, message_count, last_message_at,
               last_direction, has_pending, has_open_actions,
               folder_override, created_at, updated_at)
            VALUES
              (:id, :key, :email, :subj, :org, 'pending', 'general',
               1, NOW(), 'inbound', TRUE, FALSE, FALSE, NOW(), NOW())
            """
        ),
        {
            "id": thread_id,
            "key": f"test-{thread_id}",
            "email": "customer@test.com",
            "subj": "Test subject",
            "org": org_a.id,
        },
    )
    await db_session.commit()
    return thread_id


@pytest_asyncio.fixture
async def seeded_user(db_session, org_a):
    """Minimal user so assign_thread has a target that doesn't trigger
    the org-membership lookup path when visibility_permission is null."""
    from src.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"tech-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x",
        first_name="Test",
        last_name="Tech",
    )
    db_session.add(user)
    await db_session.commit()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_thread_emits_thread_archived_with_user_actor(
    db_session, org_a, seeded_thread, event_recorder
):
    actor = Actor(actor_type="user", user_id="user-123")

    service = AgentThreadService(db_session)
    result = await service.archive_thread(
        org_id=org_a.id, thread_id=seeded_thread, actor=actor
    )
    assert result == {"archived": True}

    event = await event_recorder.assert_emitted(
        "thread.archived", thread_id=seeded_thread
    )
    assert event["level"] == "user_action"
    assert event["actor_type"] == "user"
    assert event["actor_user_id"] == "user-123"
    assert event["organization_id"] == org_a.id
    assert event["payload"]["prior_status"] == "pending"


@pytest.mark.asyncio
async def test_archive_thread_without_actor_emits_system_action(
    db_session, org_a, seeded_thread, event_recorder
):
    service = AgentThreadService(db_session)
    await service.archive_thread(org_id=org_a.id, thread_id=seeded_thread)

    event = await event_recorder.assert_emitted(
        "thread.archived", thread_id=seeded_thread
    )
    assert event["level"] == "system_action"
    assert event["actor_type"] == "system"
    assert event["actor_user_id"] is None


@pytest.mark.asyncio
async def test_assign_thread_emits_with_prior_assignee(
    db_session, org_a, seeded_thread, seeded_user, event_recorder
):
    actor = Actor(actor_type="user", user_id="assigner-123")

    service = AgentThreadService(db_session)
    # First assignment — prior_assignee_id should be None in payload
    result = await service.assign_thread(
        org_id=org_a.id,
        thread_id=seeded_thread,
        user_id=seeded_user.id,
        user_name=f"{seeded_user.first_name} {seeded_user.last_name}",
        actor=actor,
    )
    assert result["assigned_to_user_id"] == seeded_user.id

    first = await event_recorder.assert_emitted(
        "thread.assigned", thread_id=seeded_thread, user_id=seeded_user.id
    )
    assert first["actor_user_id"] == "assigner-123"
    assert first["payload"]["prior_assignee_id"] is None


@pytest.mark.asyncio
async def test_reassign_emits_with_prior_assignee_populated(
    db_session, org_a, seeded_thread, seeded_user, event_recorder
):
    service = AgentThreadService(db_session)
    # First assignment
    await service.assign_thread(
        org_id=org_a.id, thread_id=seeded_thread, user_id=seeded_user.id,
        user_name="Tech A", actor=Actor(actor_type="user", user_id="mgr"),
    )

    # Unassign — should emit with prior_assignee_id = seeded_user.id
    await service.assign_thread(
        org_id=org_a.id, thread_id=seeded_thread, user_id=None, user_name=None,
        actor=Actor(actor_type="user", user_id="mgr"),
    )

    events = await event_recorder.all_of_type("thread.assigned")
    assert len(events) == 2
    assert events[0]["payload"]["prior_assignee_id"] is None
    assert events[1]["payload"]["prior_assignee_id"] == seeded_user.id


@pytest.mark.asyncio
async def test_archive_rolls_back_event_if_business_op_fails(
    db_session, org_a, event_recorder
):
    """Emit is inside the caller's transaction — if the business op raises,
    the event must roll back with it. Here we archive a nonexistent thread
    which raises before commit."""
    service = AgentThreadService(db_session)
    with pytest.raises(Exception):
        await service.archive_thread(
            org_id=org_a.id, thread_id="nonexistent-thread-id",
            actor=actor_system(),
        )
    await db_session.rollback()

    events = await event_recorder.all_of_type("thread.archived")
    assert events == [], "thread.archived must not persist when the business op fails"


@pytest.mark.asyncio
async def test_archive_idempotent_in_same_session(
    db_session, org_a, seeded_thread, event_recorder
):
    """Archiving a thread twice in the same session emits two events —
    there's no dedup without client_emit_id. Verifies emit doesn't
    silently merge events."""
    service = AgentThreadService(db_session)
    await service.archive_thread(org_id=org_a.id, thread_id=seeded_thread)
    await service.archive_thread(org_id=org_a.id, thread_id=seeded_thread)

    events = await event_recorder.all_of_type("thread.archived")
    assert len(events) == 2
