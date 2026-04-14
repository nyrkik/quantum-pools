"""Gmail read/unread + spam label sync — mirror QP state to Gmail.

When a thread is marked read in QP, remove the UNREAD label from all
messages in the Gmail thread. When marked unread, add it back. Same
pattern for SPAM (mark-as-spam → add SPAM + remove INBOX; mark-not-spam
→ remove SPAM + add INBOX).

Uses users.threads.modify() which applies to all messages in the thread.
Non-blocking — failures are logged but don't break QP operations.
"""

from __future__ import annotations

import asyncio
import logging

from src.models.email_integration import EmailIntegration, IntegrationStatus
from src.services.gmail.client import build_gmail_client, GmailClientError

logger = logging.getLogger(__name__)


async def sync_read_state(
    integration: EmailIntegration,
    gmail_thread_id: str,
    mark_read: bool,
) -> None:
    """Sync read/unread state to Gmail.

    Args:
        integration: Connected gmail_api EmailIntegration.
        gmail_thread_id: The Gmail thread ID.
        mark_read: True = mark read (remove UNREAD), False = mark unread (add UNREAD).
    """
    if integration.status != IntegrationStatus.connected.value:
        return
    if integration.type != "gmail_api":
        return

    try:
        client = build_gmail_client(integration)
        body = {}
        if mark_read:
            body["removeLabelIds"] = ["UNREAD"]
        else:
            body["addLabelIds"] = ["UNREAD"]

        def _modify():
            return client.users().threads().modify(
                userId="me", id=gmail_thread_id, body=body
            ).execute()

        await asyncio.to_thread(_modify)
        logger.info(f"Gmail read sync: thread={gmail_thread_id} read={mark_read}")
    except GmailClientError as e:
        logger.warning(f"Gmail read sync failed: {e}")
    except Exception as e:
        logger.warning(f"Gmail read sync error: {e}")


async def sync_spam_label(
    integration: EmailIntegration,
    gmail_thread_id: str,
    mark_spam: bool,
) -> None:
    """Mirror a QP spam decision onto the underlying Gmail thread.

    Args:
        integration: Connected gmail_api EmailIntegration.
        gmail_thread_id: The Gmail thread ID.
        mark_spam: True = add SPAM / remove INBOX, False = remove SPAM / add INBOX.
    """
    if integration.status != IntegrationStatus.connected.value:
        return
    if integration.type != "gmail_api":
        return

    try:
        client = build_gmail_client(integration)
        if mark_spam:
            body = {"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}
        else:
            body = {"addLabelIds": ["INBOX"], "removeLabelIds": ["SPAM"]}

        def _modify():
            return client.users().threads().modify(
                userId="me", id=gmail_thread_id, body=body
            ).execute()

        await asyncio.to_thread(_modify)
        logger.info(f"Gmail spam sync: thread={gmail_thread_id} spam={mark_spam}")
    except GmailClientError as e:
        logger.warning(f"Gmail spam sync failed: {e}")
    except Exception as e:
        logger.warning(f"Gmail spam sync error: {e}")
