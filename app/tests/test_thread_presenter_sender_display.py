"""Thread presenter — sender display-name fallback chain.

For unmatched senders (no matched_customer_id) the row's top-line
identity falls through: ``thread.customer_name`` → latest inbound
``AgentMessage.from_name`` → VERP-aware prettified domain. This is
how "American Express" reaches the inbox row instead of
``r_07b156d0-…@welcome.americanexpress.com``.

See docs/email-body-pipeline-refactor.md §2.3.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.presenters.thread_presenter import (
    ThreadPresenter,
    _prettify_contact_email,
)


def test_prettify_contact_email_strips_welcome_subdomain():
    assert _prettify_contact_email(
        "r_07b156d0-c180-3d87-808b@welcome.americanexpress.com",
    ) == "americanexpress.com"


def test_prettify_contact_email_strips_bouncing_subdomain():
    assert _prettify_contact_email(
        "b-1_3yynolxw2gbebhcghnoknkci2i-3hko3jaqy38ava2uk@bouncing.poolcorp.com",
    ) == "poolcorp.com"


def test_prettify_contact_email_leaves_human_address_alone():
    assert _prettify_contact_email("brian@example.com") == "brian@example.com"


def test_prettify_contact_email_handles_none_and_missing_at():
    assert _prettify_contact_email(None) is None
    assert _prettify_contact_email("") == ""
    assert _prettify_contact_email("not-an-email") == "not-an-email"


async def _seed_thread_with_message(
    db, org_id: str, *,
    matched_customer_id: str | None = None,
    thread_customer_name: str | None = None,
    from_email: str = "r_07b156d0@welcome.americanexpress.com",
    from_name: str | None = "American Express",
) -> AgentThread:
    tid = str(uuid.uuid4())
    thread = AgentThread(
        id=tid,
        organization_id=org_id,
        thread_key=f"test-sender-display|{uuid.uuid4().hex[:8]}",
        contact_email=from_email,
        subject="Remittance",
        matched_customer_id=matched_customer_id,
        customer_name=thread_customer_name,
        last_direction="inbound",
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(thread)
    await db.flush()
    db.add(AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        email_uid=f"test-{uuid.uuid4().hex[:8]}",
        direction="inbound",
        from_email=from_email,
        from_name=from_name,
        to_email="support@sapphire-pools.com",
        subject="Remittance",
        body="body",
        thread_id=tid,
        status="pending",
        received_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    return thread


@pytest.mark.asyncio
async def test_unmatched_sender_surfaces_from_name_as_customer_name(
    db_session, org_a,
):
    """Classic AmEx case — no matched customer, no thread.customer_name,
    from_name = 'American Express'. That's what the row must display."""
    thread = await _seed_thread_with_message(db_session, org_a.id)
    await db_session.commit()

    results = await ThreadPresenter(db_session).many([thread])
    assert results[0]["customer_name"] == "American Express"


@pytest.mark.asyncio
async def test_unmatched_sender_falls_back_to_pretty_domain_when_no_from_name(
    db_session, org_a,
):
    """Legacy rows — no from_name on the message. Presenter falls
    through to the VERP-aware domain prettifier."""
    thread = await _seed_thread_with_message(
        db_session, org_a.id,
        from_email="r_07b156d0@welcome.americanexpress.com",
        from_name=None,
    )
    await db_session.commit()

    results = await ThreadPresenter(db_session).many([thread])
    assert results[0]["customer_name"] == "americanexpress.com"


@pytest.mark.asyncio
async def test_unmatched_sender_thread_customer_name_wins_over_from_name(
    db_session, org_a,
):
    """If the thread already has a denormalized customer_name, keep
    it — that's usually a customer-matcher output we don't want to
    overwrite with the raw display name."""
    thread = await _seed_thread_with_message(
        db_session, org_a.id,
        thread_customer_name="Already Matched Name",
        from_name="Should Not Override",
    )
    await db_session.commit()

    results = await ThreadPresenter(db_session).many([thread])
    assert results[0]["customer_name"] == "Already Matched Name"


@pytest.mark.asyncio
async def test_from_name_equal_to_email_is_skipped(db_session, org_a):
    """Some senders set display name == email ('brian@x' <brian@x>).
    That's noise — fall through to the prettifier."""
    thread = await _seed_thread_with_message(
        db_session, org_a.id,
        from_email="brian@example.com",
        from_name="brian@example.com",
    )
    await db_session.commit()

    results = await ThreadPresenter(db_session).many([thread])
    # fell through to prettify — which is a no-op for plain human address
    assert results[0]["customer_name"] == "brian@example.com"
