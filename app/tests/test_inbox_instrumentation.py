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


@pytest.mark.asyncio
async def test_dismiss_thread_emits_status_changed(
    db_session, org_a, seeded_thread, event_recorder
):
    """Dismiss sets pending messages to ignored and records thread.status_changed
    with from/to/reason."""
    from src.services.thread_action_service import ThreadActionService

    service = ThreadActionService(db_session)
    actor = Actor(actor_type="user", user_id="dispatcher-123")
    result = await service.dismiss_thread(
        org_id=org_a.id,
        thread_id=seeded_thread,
        user_name="Test Dispatcher",
        actor=actor,
    )
    assert result == {"dismissed": True}

    event = await event_recorder.assert_emitted(
        "thread.status_changed", thread_id=seeded_thread
    )
    assert event["level"] == "user_action"
    assert event["actor_user_id"] == "dispatcher-123"
    assert event["payload"]["from"] == "pending"
    assert event["payload"]["to"] == "ignored"
    assert event["payload"]["reason"] == "dismissed"
    # No pending messages were seeded, so count is 0 — verifies the field is
    # populated, not just that pending messages dismissed.
    assert "messages_dismissed" in event["payload"]


@pytest.mark.asyncio
async def test_delete_thread_emits_thread_deleted_before_destroying(
    db_session, org_a, seeded_thread, event_recorder
):
    """delete_thread emits thread.deleted BEFORE the destructive delete, so
    the audit trail survives the loss of the thread itself. Payload captures
    message_count + status at the moment of delete."""
    service = AgentThreadService(db_session)
    actor = Actor(actor_type="user", user_id="owner-123")
    result = await service.delete_thread(
        org_id=org_a.id, thread_id=seeded_thread, actor=actor
    )
    assert result == {"deleted": True}

    event = await event_recorder.assert_emitted(
        "thread.deleted", thread_id=seeded_thread
    )
    assert event["level"] == "user_action"
    assert event["actor_user_id"] == "owner-123"
    assert event["payload"]["status_at_delete"] == "pending"
    assert event["payload"]["message_count"] == 1

    # Confirm the thread itself is gone but the event persisted.
    from sqlalchemy import text as sql_text
    thread_left = (await db_session.execute(
        sql_text("SELECT COUNT(*) FROM agent_threads WHERE id = :id"),
        {"id": seeded_thread},
    )).scalar()
    assert thread_left == 0


@pytest.mark.asyncio
async def test_delete_thread_without_actor_emits_system_action(
    db_session, org_a, seeded_thread, event_recorder
):
    service = AgentThreadService(db_session)
    await service.delete_thread(org_id=org_a.id, thread_id=seeded_thread)

    event = await event_recorder.assert_emitted(
        "thread.deleted", thread_id=seeded_thread
    )
    assert event["level"] == "system_action"
    assert event["actor_type"] == "system"


# ---------------------------------------------------------------------------
# Inbound orchestrator: _emit_agent_message_received helper
# ---------------------------------------------------------------------------


def _make_email(cc: str = "", with_attachment: bool = False):
    """Tiny email.message helper for testing the orchestrator's emit helper."""
    from email.message import EmailMessage
    em = EmailMessage()
    em["From"] = "sender@external.com"
    em["To"] = "recipient@test.com"
    em["Subject"] = "Test"
    if cc:
        em["Cc"] = cc
    em.set_content("body")
    if with_attachment:
        em.add_attachment(b"hello", maintype="application", subtype="octet-stream",
                          filename="test.bin")
    return em


@pytest.mark.asyncio
async def test_inbound_agent_message_received_helper_populates_refs(
    db_session, org_a, seeded_thread
):
    """Unit-test the orchestrator's emit helper directly. Full inbound
    pipeline is heavy to mock; this validates the shape we emit when an
    AgentMessage is created with direction='inbound'."""
    from src.models.agent_message import AgentMessage
    from src.services.agents.orchestrator import _emit_agent_message_received
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    recorder = EventRecorder(db_session)

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="webhook-abc",
        direction="inbound",
        from_email="sender@external.com",
        to_email="contact@sapphire-pools.com",
        subject="Test subject",
        body="Test body",
        thread_id=seeded_thread,
        matched_customer_id=None,
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    # Email with an attachment — helper should pick it up via walk()
    email_obj = _make_email(with_attachment=True)
    await _emit_agent_message_received(db_session, agent_msg, msg=email_obj)
    await db_session.commit()

    event = await recorder.assert_emitted(
        "agent_message.received",
        thread_id=seeded_thread,
        agent_message_id=agent_msg.id,
    )
    assert event["level"] == "system_action"
    assert event["actor_type"] == "system"
    assert event["organization_id"] == org_a.id
    assert event["payload"]["provider"] == "webhook"
    assert event["payload"]["had_attachments"] is True
    assert event["payload"]["has_cc"] is False


@pytest.mark.asyncio
async def test_inbound_helper_detects_gmail_provider(
    db_session, org_a, seeded_thread
):
    from src.models.agent_message import AgentMessage
    from src.services.agents.orchestrator import _emit_agent_message_received
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="gmail-xyz123",  # gmail- prefix → provider=gmail
        direction="inbound",
        from_email="sender@external.com",
        to_email="recipient@test.com",
        subject="",
        body="",
        thread_id=seeded_thread,
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    await _emit_agent_message_received(db_session, agent_msg, msg=_make_email())
    await db_session.commit()

    recorder = EventRecorder(db_session)
    event = await recorder.find("agent_message.received", agent_message_id=agent_msg.id)
    assert event is not None
    assert event["payload"]["provider"] == "gmail"


@pytest.mark.asyncio
async def test_classified_emits_agent_action_with_category_payload(
    db_session, org_a, seeded_thread
):
    """After classification lands on an AgentMessage, emit
    agent_message.classified with the chosen category/urgency/confidence.
    Actor is the email_classifier agent, level=agent_action."""
    from src.models.agent_message import AgentMessage
    from src.services.agents.orchestrator import _emit_agent_message_classified
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="webhook-cls",
        direction="inbound",
        from_email="sender@test.com",
        to_email="recipient@test.com",
        subject="Pool issue",
        body="There's a problem",
        thread_id=seeded_thread,
        category="service_request",
        urgency="high",
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    await _emit_agent_message_classified(db_session, agent_msg, classification_confidence="high")
    await db_session.commit()

    recorder = EventRecorder(db_session)
    event = await recorder.assert_emitted(
        "agent_message.classified",
        agent_message_id=agent_msg.id,
    )
    assert event["level"] == "agent_action"
    assert event["actor_type"] == "agent"
    assert event["actor_agent_type"] == "email_classifier"
    assert event["payload"]["category"] == "service_request"
    assert event["payload"]["urgency"] == "high"
    assert event["payload"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_classified_skipped_when_no_category(
    db_session, org_a, seeded_thread
):
    """If classification didn't produce a category, emit nothing —
    don't record a classification that didn't happen."""
    from src.models.agent_message import AgentMessage
    from src.services.agents.orchestrator import _emit_agent_message_classified
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="webhook-no-cls",
        direction="inbound",
        from_email="sender@test.com",
        to_email="recipient@test.com",
        subject="",
        body="",
        thread_id=seeded_thread,
        category=None,  # unclassified
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    await _emit_agent_message_classified(db_session, agent_msg, classification_confidence=None)
    await db_session.commit()

    recorder = EventRecorder(db_session)
    await recorder.assert_not_emitted("agent_message.classified", agent_message_id=agent_msg.id)


@pytest.mark.asyncio
async def test_customer_matched_emits_with_method_and_customer_ref(
    db_session, org_a, seeded_thread
):
    from src.models.agent_message import AgentMessage
    from src.models.customer import Customer
    from src.services.agents.orchestrator import _emit_agent_message_customer_matched
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    cust = Customer(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Matched",
        last_name="Cust",
        email="m@test.com",
        customer_type="residential",
    )
    db_session.add(cust)
    await db_session.flush()

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="webhook-matched",
        direction="inbound",
        from_email="m@test.com",
        to_email="recipient@test.com",
        subject="",
        body="",
        thread_id=seeded_thread,
        matched_customer_id=cust.id,
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    await _emit_agent_message_customer_matched(db_session, agent_msg, match_method="email")
    await db_session.commit()

    recorder = EventRecorder(db_session)
    event = await recorder.assert_emitted(
        "agent_message.customer_matched",
        agent_message_id=agent_msg.id,
        customer_id=cust.id,
    )
    assert event["level"] == "agent_action"
    assert event["actor_agent_type"] == "customer_matcher"
    assert event["payload"]["method"] == "email"


@pytest.mark.asyncio
async def test_compose_sent_emits_user_action_events_on_success(
    db_session, org_a, monkeypatch
):
    """compose_and_send emits compose.sent + agent_message.sent when the
    provider send succeeds. Both carry the sender's user_id."""
    from src.services.email_compose_service import EmailComposeService
    from src.services.email_service import EmailResult

    async def fake_send(self, *args, **kwargs):
        return EmailResult(success=True, message_id="postmark-test-id")

    monkeypatch.setattr(
        "src.services.email_service.EmailService.send_agent_reply",
        fake_send,
        raising=True,
    )

    service = EmailComposeService(db_session)
    out = await service.compose_and_send(
        org_id=org_a.id,
        to="customer@test.com",
        subject="Test",
        body="Hello",
        sender_user_id="user-abc",
        sender_name="Test User",
    )
    assert out["success"] is True

    from tests.fixtures.event_recorder import EventRecorder
    recorder = EventRecorder(db_session)

    compose_sent = await recorder.assert_emitted("compose.sent")
    assert compose_sent["level"] == "user_action"
    assert compose_sent["actor_user_id"] == "user-abc"
    assert compose_sent["payload"]["cc_added"] is False
    assert compose_sent["payload"]["attachments"] == 0

    agent_sent = await recorder.assert_emitted("agent_message.sent")
    assert agent_sent["level"] == "user_action"
    assert agent_sent["actor_user_id"] == "user-abc"


@pytest.mark.asyncio
async def test_compose_failed_emits_error_events_and_no_success_events(
    db_session, org_a, monkeypatch
):
    """Provider failure must fire agent_message.send_failed +
    error.email_send_failed — and NOT compose.sent / agent_message.sent."""
    from src.services.email_compose_service import EmailComposeService
    from src.services.email_service import EmailResult

    async def fake_send(self, *args, **kwargs):
        return EmailResult(success=False, error="Postmark rejected: invalid sender")

    monkeypatch.setattr(
        "src.services.email_service.EmailService.send_agent_reply",
        fake_send,
        raising=True,
    )

    service = EmailComposeService(db_session)
    out = await service.compose_and_send(
        org_id=org_a.id,
        to="customer@test.com",
        subject="Test",
        body="Hello",
        sender_user_id="user-xyz",
    )
    assert out["success"] is False

    from tests.fixtures.event_recorder import EventRecorder
    recorder = EventRecorder(db_session)

    # Both error events fire
    send_failed = await recorder.assert_emitted("agent_message.send_failed")
    assert send_failed["level"] == "error"
    assert "invalid sender" in send_failed["payload"]["short_error"]

    err = await recorder.assert_emitted("error.email_send_failed")
    assert err["level"] == "error"
    assert err["payload"]["provider"] == "postmark"

    # Success events must NOT fire
    await recorder.assert_not_emitted("compose.sent")
    await recorder.assert_not_emitted("agent_message.sent")


@pytest.mark.asyncio
async def test_customer_matched_skipped_when_no_match(
    db_session, org_a, seeded_thread
):
    from src.models.agent_message import AgentMessage
    from src.services.agents.orchestrator import _emit_agent_message_customer_matched
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="webhook-unmatched",
        direction="inbound",
        from_email="unknown@test.com",
        to_email="recipient@test.com",
        subject="",
        body="",
        thread_id=seeded_thread,
        matched_customer_id=None,  # no match
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    await _emit_agent_message_customer_matched(db_session, agent_msg, match_method=None)
    await db_session.commit()

    recorder = EventRecorder(db_session)
    await recorder.assert_not_emitted("agent_message.customer_matched", agent_message_id=agent_msg.id)


@pytest.mark.asyncio
async def test_inbound_helper_includes_customer_id_when_matched(
    db_session, org_a, seeded_thread
):
    """When the inbound message was matched to a customer, customer_id should
    appear in entity_refs alongside thread_id + agent_message_id."""
    from src.models.agent_message import AgentMessage
    from src.models.customer import Customer
    from src.services.agents.orchestrator import _emit_agent_message_received
    from tests.fixtures.event_recorder import EventRecorder
    import uuid as _uuid

    cust = Customer(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Test",
        last_name="Customer",
        email="test@customer.com",
        customer_type="residential",
    )
    db_session.add(cust)
    await db_session.flush()

    agent_msg = AgentMessage(
        id=str(_uuid.uuid4()),
        organization_id=org_a.id,
        email_uid="webhook-match",
        direction="inbound",
        from_email="test@customer.com",
        to_email="recipient@test.com",
        subject="",
        body="",
        thread_id=seeded_thread,
        matched_customer_id=cust.id,
        status="pending",
    )
    db_session.add(agent_msg)
    await db_session.flush()

    # Email with a Cc — helper should detect via msg.get("Cc")
    email_with_cc = _make_email(cc="another@test.com")
    await _emit_agent_message_received(db_session, agent_msg, msg=email_with_cc)
    await db_session.commit()

    recorder = EventRecorder(db_session)
    event = await recorder.find("agent_message.received", agent_message_id=agent_msg.id)
    assert event is not None
    assert event["entity_refs"]["customer_id"] == cust.id
    assert event["payload"]["has_cc"] is True
    assert event["payload"]["had_attachments"] is False
