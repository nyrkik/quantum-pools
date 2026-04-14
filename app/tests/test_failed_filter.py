"""Failed filter latest-only semantic — guards the 23→1 fix.

A thread is "failed" only if its MOST RECENT outbound attempt is in a
failure state. A successful retry resolves the thread. Without this the
filter overcounts retries-that-eventually-succeeded as losses (the bug
that showed Brian "23 failed" when only 1 was real).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


async def _make_thread_with_messages(db_session, org_id, message_specs):
    """Helper: create a thread + a sequence of outbound messages.

    message_specs: list of (status, delivery_status, minutes_offset)
    minutes_offset is added to a base time; lower = earlier.
    """
    from src.models.agent_thread import AgentThread
    from src.models.agent_message import AgentMessage

    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"f|{uuid.uuid4().hex}",
        contact_email="customer@test.com",
        subject="Test",
        message_count=len(message_specs),
        last_direction="outbound",
    )
    db_session.add(thread)
    await db_session.flush()

    base = datetime.now(timezone.utc)
    for status, dstatus, offset_min in message_specs:
        m = AgentMessage(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            thread_id=thread.id,
            direction="outbound",
            from_email="us@test.com",
            to_email="customer@test.com",
            subject="Test",
            body="x",
            status=status,
            delivery_status=dstatus,
            received_at=base + timedelta(minutes=offset_min),
        )
        db_session.add(m)
    await db_session.commit()
    return thread


@pytest.mark.asyncio
async def test_failed_filter_excludes_thread_with_later_success(db_session, org_a):
    """Thread had a failed send first, then a successful retry. Should NOT
    appear in the Failed filter — the customer got the email."""
    from src.services.agent_thread_service import AgentThreadService

    await _make_thread_with_messages(db_session, org_a.id, [
        ("failed", None, 0),    # earlier: failed
        ("sent", None, 5),      # later: success
    ])

    svc = AgentThreadService(db_session)
    result = await svc.list_threads(
        org_id=org_a.id, status="failed", search=None,
        exclude_spam=False, exclude_ignored=False, limit=50, offset=0,
    )
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_failed_filter_includes_thread_where_latest_failed(db_session, org_a):
    """Thread had a successful send, then a later failed send. SHOULD
    appear — the most recent attempt failed, customer didn't get the
    most recent email."""
    from src.services.agent_thread_service import AgentThreadService

    await _make_thread_with_messages(db_session, org_a.id, [
        ("sent", None, 0),      # earlier: success
        ("failed", None, 5),    # later: failed
    ])

    svc = AgentThreadService(db_session)
    result = await svc.list_threads(
        org_id=org_a.id, status="failed", search=None,
        exclude_spam=False, exclude_ignored=False, limit=50, offset=0,
    )
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_failed_filter_includes_bounce(db_session, org_a):
    """Most recent attempt was bounced (delivery_status='bounced')."""
    from src.services.agent_thread_service import AgentThreadService

    await _make_thread_with_messages(db_session, org_a.id, [
        ("sent", "bounced", 0),
    ])

    svc = AgentThreadService(db_session)
    result = await svc.list_threads(
        org_id=org_a.id, status="failed", search=None,
        exclude_spam=False, exclude_ignored=False, limit=50, offset=0,
    )
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_failed_filter_includes_queued(db_session, org_a):
    """Most recent attempt is stuck queued (the FB-24 phantom case before
    the janitor catches it)."""
    from src.services.agent_thread_service import AgentThreadService

    await _make_thread_with_messages(db_session, org_a.id, [
        ("queued", None, 0),
    ])

    svc = AgentThreadService(db_session)
    result = await svc.list_threads(
        org_id=org_a.id, status="failed", search=None,
        exclude_spam=False, exclude_ignored=False, limit=50, offset=0,
    )
    assert result["total"] == 1
