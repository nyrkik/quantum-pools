"""Gmail sync watermark seeding + error propagation.

Regression tests for the 2026-04-28 incident where the agent poller hammered
Gmail every minute under a 1-day list query, never seeded `last_history_id`,
and burned through the per-user rate quota. The 429s were silently swallowed
inside `_sync_query`, so the 3-strikes circuit-breaker never fired.

Pin two behaviors:
  * `_sync_query` captures the mailbox's current historyId BEFORE listing
    and persists it on success, even when the result set is empty.
  * `_sync_query` propagates HttpError from the list call so the poller's
    failure-tracking and Retry-After backoff can take action.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError
from sqlalchemy import select


def _build_client(history_id: str = "999", list_pages: list[dict] | None = None,
                  list_error: HttpError | None = None) -> MagicMock:
    """Mimic the Gmail discovery client surface that GmailSyncService touches."""
    client = MagicMock()

    profile_get = MagicMock()
    profile_get.execute = MagicMock(return_value={"historyId": history_id})
    client.users.return_value.getProfile.return_value = profile_get

    pages = list(list_pages or [{"messages": [], "resultSizeEstimate": 0}])

    def _execute_list():
        if list_error is not None:
            raise list_error
        return pages.pop(0) if pages else {"messages": []}

    list_req = MagicMock()
    list_req.execute = MagicMock(side_effect=_execute_list)
    client.users.return_value.messages.return_value.list.return_value = list_req

    return client


@pytest.mark.asyncio
async def test_sync_query_seeds_history_id_when_empty(db_session, org_a):
    """Empty mailbox still seeds last_history_id from getProfile.

    This is the bug from 2026-04-28: the watermark was never written, so the
    poller fell back to the expensive 1-day list query forever.
    """
    from src.models.email_integration import EmailIntegration, IntegrationStatus
    from src.services.gmail.sync import GmailSyncService

    integration = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        type="gmail_api",
        status=IntegrationStatus.connected.value,
        account_email="inbox@example.com",
        last_history_id=None,
    )
    db_session.add(integration)
    await db_session.commit()

    client = _build_client(history_id="42")
    svc = GmailSyncService(integration)

    with patch("src.services.gmail.sync.build_gmail_client", return_value=client):
        await svc._sync_query(client, org_a.id, "newer_than:1d")

    refreshed = (await db_session.execute(
        select(EmailIntegration).where(EmailIntegration.id == integration.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.last_history_id == "42"


@pytest.mark.asyncio
async def test_sync_query_captures_history_id_before_listing(db_session, org_a):
    """getProfile must be called before messages.list — otherwise mail that
    arrives during the scan is permanently skipped by the next incremental_sync.
    """
    from src.models.email_integration import EmailIntegration, IntegrationStatus
    from src.services.gmail.sync import GmailSyncService

    integration = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        type="gmail_api",
        status=IntegrationStatus.connected.value,
        account_email="inbox@example.com",
    )
    db_session.add(integration)
    await db_session.commit()

    call_order: list[str] = []
    client = MagicMock()

    profile_get = MagicMock()
    profile_get.execute = MagicMock(side_effect=lambda: (call_order.append("getProfile") or {"historyId": "7"}))
    client.users.return_value.getProfile.return_value = profile_get

    list_req = MagicMock()
    list_req.execute = MagicMock(side_effect=lambda: (call_order.append("list") or {"messages": []}))
    client.users.return_value.messages.return_value.list.return_value = list_req

    svc = GmailSyncService(integration)
    await svc._sync_query(client, org_a.id, "newer_than:1d")

    assert call_order[:2] == ["getProfile", "list"], (
        f"getProfile must precede the first list call, got {call_order}"
    )


@pytest.mark.asyncio
async def test_sync_query_raises_on_list_http_error(db_session, org_a):
    """A 429 (or any HttpError) during messages.list must propagate so the
    poller can count the failure and apply Retry-After backoff. Swallowing it
    is what kept the 2026-04-28 lockout extended for hours.
    """
    from src.models.email_integration import EmailIntegration, IntegrationStatus
    from src.services.gmail.sync import GmailSyncService

    integration = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        type="gmail_api",
        status=IntegrationStatus.connected.value,
        account_email="inbox@example.com",
    )
    db_session.add(integration)
    await db_session.commit()

    resp = httplib2.Response({"status": "429"})
    err = HttpError(resp, b'{"error":{"code":429,"message":"User-rate limit exceeded. Retry after 2026-04-28T10:04:16.279Z"}}')
    client = _build_client(list_error=err)

    svc = GmailSyncService(integration)
    with pytest.raises(HttpError):
        await svc._sync_query(client, org_a.id, "newer_than:1d")
