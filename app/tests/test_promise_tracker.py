"""Tests for the promise tracker — endpoints + manual set/clear.

Orchestrator-hook tests are covered by `test_followup_promise_guardrail`
+ the new in-place hook is small enough that the API tests + manual
verification suffice. Focus here is on the endpoint contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.api.deps import OrgUserContext
from src.api.v1.awaiting_reply import (
    AwaitingReplyBody,
    list_awaiting_reply,
    set_awaiting_reply,
)
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.permission import Permission
from src.models.user import User


async def _seed_user(db, org_id: str) -> OrgUserContext:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"pt-{uid[:8]}@t.com",
        hashed_password="x", first_name="P", last_name="T", is_active=True,
    ))
    org_user = OrganizationUser(
        id=str(uuid.uuid4()), organization_id=org_id, user_id=uid, role=OrgRole.owner,
    )
    db.add(org_user)
    db.add(Permission(
        id=str(uuid.uuid4()), slug="inbox.manage", resource="inbox", action="manage",
        description="Manage inbox",
    ))
    await db.flush()
    user = await db.get(User, uid)
    return OrgUserContext(user=user, org_user=org_user, org_name="Test")


async def _seed_thread(db, org_id: str, *, awaiting_until=None,
                       contact_email: str = "k@example.com",
                       subject: str = "Test promise") -> AgentThread:
    t = AgentThread(
        id=str(uuid.uuid4()), organization_id=org_id,
        thread_key=f"k-{uuid.uuid4().hex[:8]}",
        contact_email=contact_email, subject=subject,
        status="pending", category="general",
        message_count=1, last_direction="outbound",
        awaiting_reply_until=awaiting_until,
    )
    db.add(t)
    await db.flush()
    return t


# ---------------------------------------------------------------------------
# GET /v1/inbox/awaiting-reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_threads_with_overdue_flag(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    now = datetime.now(timezone.utc)

    # Overdue (3 days past)
    t1 = await _seed_thread(db_session, org_a.id, awaiting_until=now - timedelta(days=3),
                             subject="Overdue")
    # Not yet overdue (3 days future)
    t2 = await _seed_thread(db_session, org_a.id, awaiting_until=now + timedelta(days=3),
                             subject="Not yet")
    # Not awaiting at all (excluded)
    await _seed_thread(db_session, org_a.id, awaiting_until=None, subject="Excluded")
    await db_session.commit()

    out = await list_awaiting_reply(ctx=ctx, db=db_session)
    assert out["total"] == 2
    assert out["overdue_count"] == 1
    by_subject = {it["subject"]: it for it in out["items"]}
    assert by_subject["Overdue"]["is_overdue"] is True
    assert by_subject["Not yet"]["is_overdue"] is False


@pytest.mark.asyncio
async def test_list_excludes_historical_threads(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    t = await _seed_thread(
        db_session, org_a.id,
        awaiting_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    t.is_historical = True
    await db_session.commit()
    out = await list_awaiting_reply(ctx=ctx, db=db_session)
    assert out["total"] == 0


@pytest.mark.asyncio
async def test_list_org_scoped(db_session, org_a, org_b):
    """A customer-promise in org_b must not surface to org_a."""
    ctx_a = await _seed_user(db_session, org_a.id)
    await _seed_thread(
        db_session, org_b.id,
        awaiting_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    await db_session.commit()
    out = await list_awaiting_reply(ctx=ctx_a, db=db_session)
    assert out["total"] == 0


@pytest.mark.asyncio
async def test_list_includes_customer_name_when_matched(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = Customer(
        id=str(uuid.uuid4()), organization_id=org_a.id,
        first_name="Pat", last_name="M", company_name="Greystar",
    )
    db_session.add(cust)
    await db_session.flush()
    t = await _seed_thread(
        db_session, org_a.id,
        awaiting_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    t.matched_customer_id = cust.id
    await db_session.commit()
    out = await list_awaiting_reply(ctx=ctx, db=db_session)
    assert out["items"][0]["customer_name"] == "Greystar"


@pytest.mark.asyncio
async def test_list_includes_last_inbound_snippet(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    t = await _seed_thread(
        db_session, org_a.id,
        awaiting_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(AgentMessage(
        id=str(uuid.uuid4()), organization_id=org_a.id,
        direction="inbound", from_email="k@example.com",
        to_email="contact@sapphire-pools.com",
        subject="Re: Test", body="I have sent the request to my higher-up.",
        category="general", status="pending",
        thread_id=t.id, received_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()
    out = await list_awaiting_reply(ctx=ctx, db=db_session)
    assert "higher-up" in out["items"][0]["last_inbound_snippet"]


# ---------------------------------------------------------------------------
# PUT /v1/admin/agent-threads/{id}/awaiting-reply — manual snooze/clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_clears_with_null(db_session, org_a):
    """body.until = None marks the thread resolved."""
    ctx = await _seed_user(db_session, org_a.id)
    t = await _seed_thread(
        db_session, org_a.id,
        awaiting_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    await db_session.commit()
    out = await set_awaiting_reply(
        thread_id=t.id, body=AwaitingReplyBody(until=None),
        ctx=ctx, db=db_session,
    )
    assert out["awaiting_reply_until"] is None
    refreshed = await db_session.get(AgentThread, t.id)
    assert refreshed.awaiting_reply_until is None


@pytest.mark.asyncio
async def test_set_extends_window(db_session, org_a):
    """body.until = future-iso extends the window (snooze)."""
    ctx = await _seed_user(db_session, org_a.id)
    t = await _seed_thread(
        db_session, org_a.id,
        awaiting_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    new_until = datetime.now(timezone.utc) + timedelta(days=7)
    await db_session.commit()
    out = await set_awaiting_reply(
        thread_id=t.id, body=AwaitingReplyBody(until=new_until),
        ctx=ctx, db=db_session,
    )
    assert out["awaiting_reply_until"] is not None
    refreshed = await db_session.get(AgentThread, t.id)
    assert refreshed.awaiting_reply_until == new_until


@pytest.mark.asyncio
async def test_set_404_on_unknown_thread(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await set_awaiting_reply(
            thread_id=str(uuid.uuid4()),
            body=AwaitingReplyBody(until=None),
            ctx=ctx, db=db_session,
        )
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_set_404_on_cross_org_thread(db_session, org_a, org_b):
    ctx_a = await _seed_user(db_session, org_a.id)
    t_b = await _seed_thread(db_session, org_b.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await set_awaiting_reply(
            thread_id=t_b.id,
            body=AwaitingReplyBody(until=None),
            ctx=ctx_a, db=db_session,
        )
    assert e.value.status_code == 404
