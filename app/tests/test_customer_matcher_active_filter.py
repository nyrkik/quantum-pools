"""Tests for the customer matcher's email-exact-match relax.

Found via dogfood audit 2026-04-27: the matcher's step 1 + 1b had
`Customer.is_active == True` filters that silently dropped exact-email
matches when the customer was canceled. Real Sapphire impact: Jim
Stillens "Cancel Service" thread + 4 threads + 137 messages were
unmatched.

Also tests the new rematch_unmatched_messages helper that fires on
customer_contact creation to backfill late-added contacts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from sqlalchemy import select

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.customer_contact import CustomerContact
from src.services.agents.customer_matcher import rematch_unmatched_messages


async def _matched_customer_id(db, thread_id):
    """Direct SQL re-query to bypass the ORM identity-map cache after
    a raw UPDATE. db_session.get() returns stale objects."""
    return (await db.execute(
        select(AgentThread.matched_customer_id).where(AgentThread.id == thread_id)
    )).scalar()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_customer(db, org_id: str, *, email: str | None = None,
                         is_active: bool = True, company: str | None = None) -> Customer:
    c = Customer(
        id=str(uuid.uuid4()), organization_id=org_id,
        first_name="P", last_name="C", company_name=company,
        email=email, is_active=is_active,
    )
    db.add(c)
    await db.flush()
    return c


async def _seed_thread(db, org_id: str, contact_email: str) -> AgentThread:
    t = AgentThread(
        id=str(uuid.uuid4()), organization_id=org_id,
        thread_key=f"key-{uuid.uuid4().hex[:8]}",
        contact_email=contact_email, subject="Test",
        status="pending", category="general",
        message_count=1, last_direction="inbound",
    )
    db.add(t)
    await db.flush()
    return t


async def _seed_message(db, org_id: str, thread_id: str, from_email: str) -> AgentMessage:
    m = AgentMessage(
        id=str(uuid.uuid4()), organization_id=org_id,
        direction="inbound", from_email=from_email,
        to_email="contact@sapphire-pools.com",
        subject="Test", body="Test body",
        category="general", status="pending",
        thread_id=thread_id,
        received_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


# ---------------------------------------------------------------------------
# rematch_unmatched_messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rematch_links_existing_unmatched_threads_and_messages(db_session, org_a):
    """Late-added contact: customer + thread/message exist but
    matched_customer_id is null. Calling rematch links them."""
    cust = await _seed_customer(db_session, org_a.id, company="Test PM")
    t1 = await _seed_thread(db_session, org_a.id, "kim@example.com")
    await _seed_message(db_session, org_a.id, t1.id, "kim@example.com")
    t2 = await _seed_thread(db_session, org_a.id, "kim@example.com")
    await _seed_message(db_session, org_a.id, t2.id, "kim@example.com")
    # Different sender — must NOT be linked
    t3 = await _seed_thread(db_session, org_a.id, "other@example.com")
    await _seed_message(db_session, org_a.id, t3.id, "other@example.com")
    await db_session.commit()

    threads_linked, messages_linked = await rematch_unmatched_messages(
        db_session,
        organization_id=org_a.id,
        email="kim@example.com",
        customer_id=cust.id,
    )
    await db_session.commit()
    assert threads_linked == 2
    assert messages_linked == 2

    assert await _matched_customer_id(db_session, t1.id) == cust.id
    assert await _matched_customer_id(db_session, t3.id) is None  # different sender


@pytest.mark.asyncio
async def test_rematch_case_insensitive_email(db_session, org_a):
    cust = await _seed_customer(db_session, org_a.id)
    t = await _seed_thread(db_session, org_a.id, "User@Example.com")
    await _seed_message(db_session, org_a.id, t.id, "User@Example.com")
    await db_session.commit()
    out = await rematch_unmatched_messages(
        db_session,
        organization_id=org_a.id,
        email="user@example.com",  # lowercase
        customer_id=cust.id,
    )
    await db_session.commit()
    assert out == (1, 1)


@pytest.mark.asyncio
async def test_rematch_skips_already_matched(db_session, org_a):
    """Re-running rematch on already-linked threads is a no-op."""
    existing_cust = await _seed_customer(db_session, org_a.id, company="Existing")
    new_cust = await _seed_customer(db_session, org_a.id, company="New")
    t = await _seed_thread(db_session, org_a.id, "kim@example.com")
    t.matched_customer_id = existing_cust.id
    await _seed_message(db_session, org_a.id, t.id, "kim@example.com")
    await db_session.commit()
    out = await rematch_unmatched_messages(
        db_session, organization_id=org_a.id,
        email="kim@example.com", customer_id=new_cust.id,
    )
    await db_session.commit()
    assert out[0] == 0  # thread already had matched_customer_id; rematch left it alone
    # Pre-existing match preserved
    assert await _matched_customer_id(db_session, t.id) == existing_cust.id


@pytest.mark.asyncio
async def test_rematch_org_scoped(db_session, org_a, org_b):
    """An email match in org_b must NOT be touched by an org_a rematch."""
    cust_a = await _seed_customer(db_session, org_a.id)
    cust_b = await _seed_customer(db_session, org_b.id)
    t_a = await _seed_thread(db_session, org_a.id, "shared@example.com")
    t_b = await _seed_thread(db_session, org_b.id, "shared@example.com")
    await db_session.commit()
    await rematch_unmatched_messages(
        db_session, organization_id=org_a.id,
        email="shared@example.com", customer_id=cust_a.id,
    )
    await db_session.commit()
    assert await _matched_customer_id(db_session, t_a.id) == cust_a.id
    assert await _matched_customer_id(db_session, t_b.id) is None  # org_b unaffected


@pytest.mark.asyncio
async def test_rematch_skips_historical_threads(db_session, org_a):
    """Historical-import threads are deliberately isolated; never rematch them."""
    cust = await _seed_customer(db_session, org_a.id)
    t = await _seed_thread(db_session, org_a.id, "kim@example.com")
    t.is_historical = True
    await db_session.commit()
    out = await rematch_unmatched_messages(
        db_session, organization_id=org_a.id,
        email="kim@example.com", customer_id=cust.id,
    )
    await db_session.commit()
    assert out[0] == 0


@pytest.mark.asyncio
async def test_rematch_handles_empty_email(db_session, org_a):
    cust = await _seed_customer(db_session, org_a.id)
    out = await rematch_unmatched_messages(
        db_session, organization_id=org_a.id,
        email="", customer_id=cust.id,
    )
    assert out == (0, 0)
