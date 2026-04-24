"""Regression test — `process_incoming_email` must not UnboundLocalError
on the known-customer ingest path.

Bug history: between Phase 5 Steps 3 and 5 the `unverified_candidates`
list was initialized inside `if not sender_is_customer:` but read later
unconditionally at the proposal-staging block. Every inbound from an
already-matched customer tripped a NameError, and Sapphire's agent
service error-looped for ~17 min until the one-line hoist shipped.

The fix is trivial; the guard is not. We want confidence the known-
customer branch continues to run end-to-end as the orchestrator grows.
This test exercises that branch by:

1. Seeding an existing `AgentThread` with `matched_customer_id` set,
   which makes `sender_is_customer` True at line 521.
2. Passing `gmail_labels=["SPAM"]` so the classifier is bypassed
   (the synthetic spam result keeps the path deterministic without
   mocking Claude).
3. Monkey-patching `ai_triage` so there's no outbound network call.
4. Calling `process_incoming_email` and asserting it completes
   without raising.

The known-customer override (orchestrator.py around line 668) flips
the classifier's `spam` result to `general` + `pending`, which drops
the flow through the proposal-staging block — the exact site that
previously tripped the bug.
"""

from __future__ import annotations

import uuid
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.services.agents import orchestrator
from src.services.agents import triage_agent
from src.utils.thread_utils import make_thread_key


CUSTOMER_EMAIL = "regression-test@example.com"
THREAD_SUBJECT = "existing thread subject"


async def _seed_known_customer(db, org_id: str) -> tuple[Customer, AgentThread]:
    cust = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        first_name="Regression",
        last_name="Test",
        email=CUSTOMER_EMAIL,
        customer_type="residential",
    )
    db.add(cust)
    await db.flush()
    # thread_key MUST match what `get_or_create_thread` computes from
    # the inbound's (from_email, subject) so the orchestrator picks up
    # this pre-seeded thread (with matched_customer_id) instead of
    # creating a fresh unmatched one.
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=make_thread_key(CUSTOMER_EMAIL, THREAD_SUBJECT),
        contact_email=CUSTOMER_EMAIL,
        subject=THREAD_SUBJECT,
        matched_customer_id=cust.id,
        customer_name=f"{cust.first_name} {cust.last_name}",
        status="handled",
        message_count=0,
    )
    db.add(thread)
    await db.commit()
    return cust, thread


def _build_inbound(from_email: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = "support@sapphire-pools.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = f"<{uuid.uuid4()}@example.com>"
    msg.set_content(body)
    return msg


@pytest.mark.asyncio
async def test_known_customer_inbound_does_not_unbound_local_error(
    db_session, org_a, monkeypatch,
):
    """Repro for the 2026-04-24 prod regression. Without the variable-scope
    fix this raises `UnboundLocalError: cannot access local variable
    'unverified_candidates' where it is not associated with a value`."""

    cust, _thread = await _seed_known_customer(db_session, org_a.id)

    # Stub ai_triage — avoids a live Claude call during the test.
    async def _fake_triage(body: str, subject: str, from_email: str) -> bool:
        return True

    monkeypatch.setattr(triage_agent, "ai_triage", _fake_triage)
    monkeypatch.setattr(orchestrator, "ai_triage", _fake_triage, raising=False)

    msg = _build_inbound(cust.email, f"Re: {THREAD_SUBJECT}", "hello")
    uid = f"test-regression-{uuid.uuid4().hex[:8]}"

    # gmail_labels=["SPAM"] bypasses classify_and_draft and makes the
    # known-customer override branch take over (category spam→general
    # for matched customers) — driving flow through the previously-
    # tripping proposal-staging block WITHOUT needing Claude.
    await orchestrator.process_incoming_email(
        uid, msg,
        organization_id=org_a.id,
        gmail_labels=["SPAM"],
    )

    # Sanity: the ingest persisted an AgentMessage on the existing thread.
    rows = (await db_session.execute(
        select(AgentMessage).where(AgentMessage.email_uid == uid)
    )).scalars().all()
    assert len(rows) == 1, "inbound AgentMessage should have been created"
    assert rows[0].matched_customer_id == cust.id or rows[0].from_email == cust.email
