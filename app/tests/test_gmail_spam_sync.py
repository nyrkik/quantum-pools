"""Gmail spam sync + retention behavior.

Exercises the 2026-04-14 Gmail-spam visibility feature:
  * 30-day retention purges old spam threads and leaves newer / non-spam alone
  * Threads with attached AgentAction rows are skipped to avoid FK violations
  * sync_spam_label sends the correct add/remove label pair to Gmail

Note: end-to-end tests of the orchestrator's Gmail-flagged-spam bypass and
of the history-sync label handler require substantial Gmail API mocking and
live in the deploy smoke test, not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select


async def _make_spam_thread(db_session, org_id: str, *, age_days: float, has_action: bool = False):
    from src.models.agent_action import AgentAction
    from src.models.agent_message import AgentMessage
    from src.models.agent_thread import AgentThread

    now = datetime.now(timezone.utc)
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"spam|{uuid.uuid4().hex}",
        contact_email="spammer@bad.example",
        subject="Totally not spam",
        category="spam",
        message_count=1,
        last_direction="inbound",
        last_message_at=now - timedelta(days=age_days),
    )
    db_session.add(thread)
    await db_session.flush()

    db_session.add(AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        email_uid=f"uid-{uuid.uuid4().hex}",
        thread_id=thread.id,
        direction="inbound",
        from_email="spammer@bad.example",
        to_email="inbox@example.com",
        subject="Totally not spam",
        body="body",
        category="spam",
        status="handled",
        received_at=now - timedelta(days=age_days),
    ))
    if has_action:
        db_session.add(AgentAction(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            thread_id=thread.id,
            action_type="other",
            description="Orphaned action on spam thread",
            status="open",
        ))
    await db_session.commit()
    return thread


@pytest.mark.asyncio
async def test_retention_purges_old_spam(db_session, org_a):
    from src.models.agent_thread import AgentThread
    from app import _run_spam_retention

    old = await _make_spam_thread(db_session, org_a.id, age_days=45)
    new = await _make_spam_thread(db_session, org_a.id, age_days=10)

    await _run_spam_retention()

    remaining = (await db_session.execute(select(AgentThread.id))).scalars().all()
    assert old.id not in remaining
    assert new.id in remaining


@pytest.mark.asyncio
async def test_retention_leaves_non_spam_alone(db_session, org_a):
    """Non-spam threads older than 30 days must not be touched."""
    from src.models.agent_thread import AgentThread
    from app import _run_spam_retention

    now = datetime.now(timezone.utc)
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        thread_key=f"keep|{uuid.uuid4().hex}",
        contact_email="customer@ok.example",
        subject="Real mail",
        category="general",
        message_count=1,
        last_direction="inbound",
        last_message_at=now - timedelta(days=90),
    )
    db_session.add(thread)
    await db_session.commit()

    await _run_spam_retention()

    assert (await db_session.execute(
        select(AgentThread.id).where(AgentThread.id == thread.id)
    )).scalar_one_or_none() == thread.id


@pytest.mark.asyncio
async def test_retention_skips_threads_with_actions(db_session, org_a):
    """FK safety: old spam with attached AgentAction must not be deleted."""
    from src.models.agent_thread import AgentThread
    from app import _run_spam_retention

    protected = await _make_spam_thread(db_session, org_a.id, age_days=45, has_action=True)

    await _run_spam_retention()

    assert (await db_session.execute(
        select(AgentThread.id).where(AgentThread.id == protected.id)
    )).scalar_one_or_none() == protected.id


@pytest.mark.asyncio
async def test_sync_spam_label_applies_correct_labels():
    """mark_spam=True → add SPAM + remove INBOX; False → the inverse."""
    from src.models.email_integration import EmailIntegration, IntegrationStatus
    from src.services.gmail.read_sync import sync_spam_label

    integration = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        type="gmail_api",
        status=IntegrationStatus.connected.value,
        account_email="inbox@example.com",
    )

    client = MagicMock()
    modify = MagicMock()
    modify.execute = MagicMock(return_value={})
    client.users.return_value.threads.return_value.modify.return_value = modify

    with patch("src.services.gmail.read_sync.build_gmail_client", return_value=client):
        await sync_spam_label(integration, "gmail-thread-123", mark_spam=True)
        call_body = client.users.return_value.threads.return_value.modify.call_args.kwargs["body"]
        assert call_body == {"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}

        await sync_spam_label(integration, "gmail-thread-123", mark_spam=False)
        call_body = client.users.return_value.threads.return_value.modify.call_args.kwargs["body"]
        assert call_body == {"addLabelIds": ["INBOX"], "removeLabelIds": ["SPAM"]}


@pytest.mark.asyncio
async def test_sync_spam_label_noop_when_disconnected():
    """No Gmail API call when integration isn't connected."""
    from src.models.email_integration import EmailIntegration, IntegrationStatus
    from src.services.gmail.read_sync import sync_spam_label

    integration = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        type="gmail_api",
        status=IntegrationStatus.error.value,  # not connected
        account_email="inbox@example.com",
    )

    builder = MagicMock()
    with patch("src.services.gmail.read_sync.build_gmail_client", builder):
        await sync_spam_label(integration, "gmail-thread-123", mark_spam=True)
        builder.assert_not_called()
