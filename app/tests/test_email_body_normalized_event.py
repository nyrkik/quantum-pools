"""`email.body_normalized` fires when ingest had to repair a body.

This is the observability hook for the "next Yardi-class quirk" —
if a new sender shows up with a body that needs QP decode or HTML
stripping, we want it in `platform_events` immediately so we can
find it with a GROUP BY without waiting for a user complaint.

Tests exercise the emit path from `_emit_agent_message_received`
directly (narrow, deterministic) rather than the full
`process_incoming_email` flow (too many moving parts for this
slice of behavior).
"""

from __future__ import annotations

import uuid

import pytest

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.services.agents.orchestrator import _emit_agent_message_received


async def _seed_thread_and_message(db, org_id: str) -> AgentMessage:
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"test-body-normalized|{uuid.uuid4().hex[:8]}",
        contact_email="sender@example.com",
        subject="test",
        last_snippet="short",
    )
    db.add(thread)
    await db.flush()
    msg = AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        email_uid=f"pm-{uuid.uuid4().hex}",
        direction="inbound",
        from_email="DoNotReply@Yardi.com",
        to_email="support@sapphire-pools.com",
        subject="Remittance",
        body="Payment Overview",
        thread_id=thread.id,
        status="pending",
    )
    db.add(msg)
    await db.flush()
    return msg


@pytest.mark.asyncio
async def test_email_body_normalized_emitted_when_flags_present(
    db_session, org_a, event_recorder,
):
    msg = await _seed_thread_and_message(db_session, org_a.id)
    await _emit_agent_message_received(
        db_session, msg, msg=None,
        body_normalize_flags={
            "mime_unwrapped": False,
            "qp_decoded": True,
            "html_stripped_from_text": True,
        },
    )
    await db_session.commit()

    events = await event_recorder.all_of_type("email.body_normalized")
    assert len(events) == 1
    ev = events[0]
    assert ev["entity_refs"]["thread_id"] == msg.thread_id
    assert ev["entity_refs"]["agent_message_id"] == msg.id
    # Flags that fired are in the payload; flags that didn't are absent.
    assert ev["payload"]["qp_decoded"] is True
    assert ev["payload"]["html_stripped_from_text"] is True
    assert "mime_unwrapped" not in ev["payload"]
    # Domain only — never the full email address.
    assert ev["payload"]["from_email_domain"] == "yardi.com"


@pytest.mark.asyncio
async def test_email_body_normalized_silent_when_all_flags_false(
    db_session, org_a, event_recorder,
):
    msg = await _seed_thread_and_message(db_session, org_a.id)
    await _emit_agent_message_received(
        db_session, msg, msg=None,
        body_normalize_flags={
            "mime_unwrapped": False,
            "qp_decoded": False,
            "html_stripped_from_text": False,
        },
    )
    await db_session.commit()

    events = await event_recorder.all_of_type("email.body_normalized")
    assert events == []


@pytest.mark.asyncio
async def test_email_body_normalized_silent_when_flags_none(
    db_session, org_a, event_recorder,
):
    msg = await _seed_thread_and_message(db_session, org_a.id)
    await _emit_agent_message_received(
        db_session, msg, msg=None, body_normalize_flags=None,
    )
    await db_session.commit()

    events = await event_recorder.all_of_type("email.body_normalized")
    assert events == []
