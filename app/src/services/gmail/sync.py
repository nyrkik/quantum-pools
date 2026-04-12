"""Gmail inbound sync — pull messages into AgentMessage records.

Two modes:

1. **Initial sync** — first time we connect, pull the last N days of mail
   (default 30) so the user immediately sees their existing customer email.
   Walks `users.messages.list()` paginated, fetches each via
   `users.messages.get(format='raw')`, and feeds the raw RFC 5322 bytes
   into the existing inbound pipeline (`process_incoming_email`) so the
   message goes through customer matching, threading, classification, etc.

2. **Incremental sync** — uses `users.history.list(startHistoryId=...)`
   to fetch only changes since the last sync. Cheaper than re-listing.
   Falls back to a date-bounded list if the historyId has expired
   (Gmail expires history after ~1 week of no calls).

Eventually this will be replaced (or supplemented) by Pub/Sub push
notifications for true real-time. For now polling on a short cadence is
simpler and good enough.
"""

from __future__ import annotations

import asyncio
import base64
import email
import hashlib
import logging
from datetime import datetime, timezone

from googleapiclient.errors import HttpError
from sqlalchemy import select

from src.core.database import get_db_context
from src.models.agent_message import AgentMessage
from src.models.email_integration import EmailIntegration, IntegrationStatus
from src.services.gmail.client import build_gmail_client, GmailClientError

logger = logging.getLogger(__name__)


class GmailSyncService:
    """Pull messages from a connected Gmail account into AgentMessage records."""

    def __init__(self, integration: EmailIntegration):
        if integration.type != "gmail_api":
            raise ValueError(f"integration {integration.id} is not gmail_api")
        self.integration = integration

    async def initial_sync(self, days: int = 30) -> dict:
        """Pull the last `days` days of inbox + sent mail. Idempotent — re-running
        re-imports the same messages but the dedup-by-inspection_id-equivalent
        on AgentMessage.email_uid prevents duplicates.

        Returns stats: {fetched, ingested, skipped, errors}
        """
        client = build_gmail_client(self.integration)
        org_id = self.integration.organization_id
        query = f"newer_than:{days}d"

        return await self._sync_query(client, org_id, query, historical=True)

    async def incremental_sync(self) -> dict:
        """Fetch changes since the last successful sync via Gmail history API.

        Falls back to a 1-day window list if no history_id is set or if
        the stored history_id has expired.
        """
        client = build_gmail_client(self.integration)
        org_id = self.integration.organization_id

        last_history_id = self.integration.last_history_id
        if not last_history_id:
            logger.info(f"No last_history_id for integration {self.integration.id} — falling back to 1-day window")
            return await self._sync_query(client, org_id, "newer_than:1d")

        try:
            return await self._sync_history(client, org_id, last_history_id)
        except HttpError as e:
            if "404" in str(e) or "history" in str(e).lower():
                logger.warning(
                    f"history_id expired for integration {self.integration.id} — full re-sync window"
                )
                return await self._sync_query(client, org_id, "newer_than:1d")
            raise

    async def _sync_query(self, client, org_id: str, query: str, historical: bool = False) -> dict:
        """Walk users.messages.list with a Gmail search query and ingest each."""
        stats = {"fetched": 0, "ingested": 0, "skipped": 0, "errors": 0}

        def _list_page(page_token=None):
            req = client.users().messages().list(
                userId="me", q=query, maxResults=100, pageToken=page_token
            )
            return req.execute()

        page_token = None
        latest_history_id = self.integration.last_history_id
        while True:
            try:
                resp = await asyncio.to_thread(_list_page, page_token)
            except HttpError as e:
                logger.error(f"Gmail list failed: {e}")
                stats["errors"] += 1
                break

            messages = resp.get("messages", [])
            if not messages:
                break

            for m in messages:
                try:
                    ingested = await self._fetch_and_ingest(client, org_id, m["id"], historical=historical)
                    stats["fetched"] += 1
                    if ingested:
                        stats["ingested"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    logger.warning(f"Gmail ingest failed for {m.get('id')}: {e}")
                    stats["errors"] += 1

            # Track latest historyId we've seen so we can resume incrementally
            if resp.get("resultSizeEstimate") and messages:
                # Need to fetch one message to read its historyId — we already
                # did that inside _fetch_and_ingest, so use the integration's
                # current value (updated by the last ingest)
                pass

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # Update integration sync state
        async with get_db_context() as db:
            row = (await db.execute(
                select(EmailIntegration).where(EmailIntegration.id == self.integration.id)
            )).scalar_one_or_none()
            if row:
                row.last_sync_at = datetime.now(timezone.utc)
                row.status = IntegrationStatus.connected.value
                row.last_error = None
                row.last_error_at = None
                if latest_history_id:
                    row.last_history_id = latest_history_id
                await db.commit()

        return stats

    async def _sync_history(self, client, org_id: str, start_history_id: str) -> dict:
        """Use users.history.list to find changes since start_history_id."""
        stats = {"fetched": 0, "ingested": 0, "skipped": 0, "errors": 0}

        def _hist_page(page_token=None):
            req = client.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            )
            return req.execute()

        page_token = None
        latest_history_id = start_history_id
        while True:
            resp = await asyncio.to_thread(_hist_page, page_token)
            history = resp.get("history", [])
            if resp.get("historyId"):
                latest_history_id = resp["historyId"]

            for h in history:
                for ma in h.get("messagesAdded", []):
                    msg = ma.get("message", {})
                    msg_id = msg.get("id")
                    if not msg_id:
                        continue
                    try:
                        ingested = await self._fetch_and_ingest(client, org_id, msg_id)
                        stats["fetched"] += 1
                        if ingested:
                            stats["ingested"] += 1
                        else:
                            stats["skipped"] += 1
                    except Exception as e:
                        logger.warning(f"Gmail history ingest failed for {msg_id}: {e}")
                        stats["errors"] += 1

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # Persist the new historyId so the next incremental sync resumes here
        async with get_db_context() as db:
            row = (await db.execute(
                select(EmailIntegration).where(EmailIntegration.id == self.integration.id)
            )).scalar_one_or_none()
            if row:
                row.last_sync_at = datetime.now(timezone.utc)
                row.last_history_id = latest_history_id
                row.status = IntegrationStatus.connected.value
                await db.commit()

        return stats

    async def _fetch_and_ingest(self, client, org_id: str, gmail_message_id: str, historical: bool = False) -> bool:
        """Fetch a single Gmail message in raw form, dedupe, and feed it
        into the existing inbound pipeline.

        Returns True if a new AgentMessage was created, False if skipped.
        """
        # Stable UID derived from Gmail's own message ID
        uid = f"gm-{hashlib.sha256(gmail_message_id.encode()).hexdigest()[:32]}"

        # Skip if already ingested
        async with get_db_context() as db:
            existing = (await db.execute(
                select(AgentMessage.id).where(AgentMessage.email_uid == uid).limit(1)
            )).first()
            if existing:
                return False

        def _get():
            return client.users().messages().get(
                userId="me", id=gmail_message_id, format="raw"
            ).execute()

        msg_data = await asyncio.to_thread(_get)

        raw_b64 = msg_data.get("raw", "")
        if not raw_b64:
            logger.warning(f"Gmail message {gmail_message_id} has no raw body")
            return False

        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        email_msg = email.message_from_bytes(raw_bytes)

        from src.services.agents.orchestrator import process_incoming_email
        try:
            await process_incoming_email(uid, email_msg, organization_id=org_id, historical=historical)
            return True
        except Exception as e:
            logger.error(f"process_incoming_email failed for {uid}: {e}")
            raise
