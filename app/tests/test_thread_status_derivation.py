"""Regression guard for the new `update_thread_status` derivation.

Pre-2026-04-25 the field encoded two orthogonal questions in one
string: "needs attention?" AND "did we send a reply?". When the
classifier auto-closed an inbound without sending (informational mail),
the resulting `status="ignored"` made the thread invisible behind the
default Inbox query.

The new derivation:

    has_pending           → "pending"
    has_outcome           → "handled"
        (sent OR auto_sent OR an inbound `status='handled'`)
    else                  → "archived"

`ignored` is no longer derived. AI-auto-close visibility lives on
`auto_handled_at` instead.

These four tests pin the derivation against future regressions, and the
fifth pins the dismiss-thread path that previously produced the
conflated `status='ignored'` (now naturally derives to `archived`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.services.agents.thread_manager import update_thread_status


def _make_thread(org_id: str) -> AgentThread:
    return AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"derivation|{uuid.uuid4().hex[:8]}",
        contact_email="sender@example.com",
        subject="Test",
        status="pending",
        has_pending=True,
        last_message_at=datetime.now(timezone.utc),
    )


def _make_msg(thread_id: str, org_id: str, *, direction: str, status: str) -> AgentMessage:
    return AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_id=thread_id,
        email_uid=f"uid|{uuid.uuid4().hex[:8]}",
        direction=direction,
        status=status,
        from_email="sender@example.com",
        to_email="us@example.com",
        subject="Test",
        body="body",
        received_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_pending_when_any_message_pending(db_session, org_a):
    t = _make_thread(org_a.id)
    db_session.add(t)
    db_session.add(_make_msg(t.id, org_a.id, direction="inbound", status="pending"))
    await db_session.commit()

    await update_thread_status(t.id)
    await db_session.refresh(t)
    assert t.status == "pending"
    assert t.has_pending is True


@pytest.mark.asyncio
async def test_handled_when_inbound_auto_closed(db_session, org_a):
    """The original miss case — informational inbound, AI marks it
    handled, no reply sent. Pre-fix this derived to `ignored` and the
    Inbox query hid it. Now it stays in Handled where users can find it."""
    t = _make_thread(org_a.id)
    db_session.add(t)
    db_session.add(_make_msg(t.id, org_a.id, direction="inbound", status="handled"))
    await db_session.commit()

    await update_thread_status(t.id)
    await db_session.refresh(t)
    assert t.status == "handled"
    assert t.has_pending is False


@pytest.mark.asyncio
async def test_handled_when_outbound_sent(db_session, org_a):
    """Human (or pre-approval AI) sent a reply — classic Handled."""
    t = _make_thread(org_a.id)
    db_session.add(t)
    db_session.add(_make_msg(t.id, org_a.id, direction="inbound", status="handled"))
    db_session.add(_make_msg(t.id, org_a.id, direction="outbound", status="sent"))
    await db_session.commit()

    await update_thread_status(t.id)
    await db_session.refresh(t)
    assert t.status == "handled"


@pytest.mark.asyncio
async def test_archived_when_user_dismissed(db_session, org_a):
    """The Dismiss thread path stamps msg.status='ignored'. The new
    derivation has no inbound `handled` and no outbound sent, so the
    thread derives to `archived` — no longer the conflated `ignored`
    that pre-2026-04-25 hid AI auto-closes."""
    t = _make_thread(org_a.id)
    db_session.add(t)
    db_session.add(_make_msg(t.id, org_a.id, direction="inbound", status="ignored"))
    await db_session.commit()

    await update_thread_status(t.id)
    await db_session.refresh(t)
    assert t.status == "archived"
