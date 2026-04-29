"""Gmail push notifications via Cloud Pub/Sub.

`users.watch()` subscribes a mailbox to push notifications. When mail
lands or any change happens, Gmail publishes to our Pub/Sub topic;
Pub/Sub HTTP-POSTs our public webhook with the new historyId. We call
`history.list(historyId)` (the cheap path we already use for incremental
sync) and ingest via the existing pipeline.

Why this exists: 60s polling burned a fixed ~24h user-rate-limit bucket
on 2026-04-28 when the watermark wasn't persisting. With watch + push,
quota usage drops to ~365 calls/year (one watch refresh per day) plus
the actual history.list calls when changes happen — lockouts become
structurally impossible.

Watch expires hard at 7 days. Daily refresh job (`agent_poller`) calls
`refresh_watch` to roll the expiry forward. If the refresh lapses for
>7d, push silently stops — covered by `last_pubsub_push_at` heartbeat
alert in the poller.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from googleapiclient.errors import HttpError
from sqlalchemy import select

from src.core.database import get_db_context
from src.models.email_integration import EmailIntegration
from src.services.gmail.client import build_gmail_client, GmailClientError
from src.services.gmail.rate_limit import (
    is_gmail_rate_limited,
    record_gmail_rate_limit,
    parse_gmail_retry_after,
)

logger = logging.getLogger(__name__)


# Gmail history types we want pushes for. messageAdded covers new mail;
# labelAdded/labelRemoved covers SPAM transitions and any future label-
# based UX (already handled in `sync._sync_history`).
_LABEL_FILTER = ["INBOX", "SPAM"]


async def setup_watch(integration: EmailIntegration, *, topic_name: str) -> dict:
    """Subscribe the mailbox to push notifications. Stores topic + expiry.

    Args:
        integration: connected gmail_api EmailIntegration row
        topic_name: full Pub/Sub topic path,
            "projects/{project-id}/topics/{topic}"

    Returns:
        Gmail's response: {historyId, expiration}. Expiration is ms-since-epoch.

    Raises:
        GmailClientError on API failure (including 429 — caller should
        respect any rate-limit park already in effect).
    """
    if await is_gmail_rate_limited(integration.id):
        raise GmailClientError(
            f"Gmail integration {integration.id} is rate-limited — watch setup aborted"
        )

    client = build_gmail_client(integration)

    body = {
        "topicName": topic_name,
        "labelIds": _LABEL_FILTER,
        "labelFilterBehavior": "INCLUDE",
    }

    def _watch():
        return client.users().watch(userId="me", body=body).execute()

    try:
        result = await asyncio.to_thread(_watch)
    except HttpError as e:
        retry_at = parse_gmail_retry_after(e)
        if retry_at:
            await record_gmail_rate_limit(integration.id, retry_at)
        raise GmailClientError(f"Gmail watch setup failed: {e}") from e

    expiration_ms = int(result.get("expiration", 0))
    history_id = result.get("historyId")
    expires_at = (
        datetime.fromtimestamp(expiration_ms / 1000.0, tz=timezone.utc)
        if expiration_ms else None
    )

    async with get_db_context() as db:
        row = (await db.execute(
            select(EmailIntegration).where(EmailIntegration.id == integration.id)
        )).scalar_one_or_none()
        if row:
            row.pubsub_topic_name = topic_name
            row.watch_expires_at = expires_at
            row.last_watch_refresh_at = datetime.now(timezone.utc)
            # Seed the watermark too — Gmail's watch response carries
            # the current historyId; subsequent pushes reference deltas
            # from this point. Without this, the first push has no
            # baseline to history.list() against.
            if history_id and not row.last_history_id:
                row.last_history_id = str(history_id)
            await db.commit()

    logger.info(
        f"Gmail watch set up: integration={integration.id} topic={topic_name} "
        f"expires={expires_at.isoformat() if expires_at else 'unknown'} "
        f"history_id={history_id}"
    )
    return result


async def refresh_watch(integration: EmailIntegration) -> dict | None:
    """Re-call users.watch using the integration's stored topic.

    Idempotent — Gmail accepts repeated watch calls and just returns a
    fresh expiry. No-op if topic_name is NULL (push not enabled for
    this integration).
    """
    if not integration.pubsub_topic_name:
        return None
    return await setup_watch(integration, topic_name=integration.pubsub_topic_name)


async def stop_watch(integration: EmailIntegration) -> None:
    """Tear down the watch (e.g. on disconnect).

    Calls users.stop. Safe to call when no watch exists — Gmail returns
    204 either way. Clears the persisted topic + expiry.
    """
    if integration.type != "gmail_api":
        return

    if await is_gmail_rate_limited(integration.id):
        # Don't poke a throttled bucket just to stop a watch. The watch
        # will expire on its own at watch_expires_at.
        logger.info(f"Skipping stop_watch for {integration.id} — rate-limit park active")
    else:
        try:
            client = build_gmail_client(integration)

            def _stop():
                return client.users().stop(userId="me").execute()

            await asyncio.to_thread(_stop)
            logger.info(f"Gmail watch stopped: integration={integration.id}")
        except HttpError as e:
            retry_at = parse_gmail_retry_after(e)
            if retry_at:
                await record_gmail_rate_limit(integration.id, retry_at)
            logger.warning(f"Gmail stop_watch failed (non-fatal): {e}")
        except Exception as e:
            logger.warning(f"Gmail stop_watch error (non-fatal): {e}")

    async with get_db_context() as db:
        row = (await db.execute(
            select(EmailIntegration).where(EmailIntegration.id == integration.id)
        )).scalar_one_or_none()
        if row:
            row.pubsub_topic_name = None
            row.pubsub_subscription_name = None
            row.watch_expires_at = None
            await db.commit()
