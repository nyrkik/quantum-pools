"""Shared Gmail rate-limit parking — all paths use this.

Background: 2026-04-28 lockout was extended by retries hitting Google's
fixed ~24h user-rate-limit bucket. The poller fix (in-memory parking)
worked for inbound but didn't cover outbound send or read/spam mirror —
both can hit the same per-user quota and burn another 24h dark window
on bulk sends or sweeps. This module gives every Gmail path a shared
park-until-T signal stored on `email_integrations.gmail_retry_after_at`.

Usage from any path that calls Gmail API:

    from src.services.gmail.rate_limit import (
        is_gmail_rate_limited,
        record_gmail_rate_limit,
        parse_gmail_retry_after,
    )

    if await is_gmail_rate_limited(integration_id):
        raise GmailClientError("Gmail rate-limit park active")

    try:
        ...gmail call...
    except HttpError as e:
        retry_at = parse_gmail_retry_after(e)
        if retry_at:
            await record_gmail_rate_limit(integration_id, retry_at)
        raise

The 24h-bucket nature of Google's user rate limit means we want
ALL Gmail traffic for the same integration to halt the moment one path
gets a 429, not just the path that triggered it.
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.email_integration import EmailIntegration

logger = logging.getLogger(__name__)


# Permissive ISO-8601 timestamp anchor used in the user-rate-limit body.
# Google's body text format: "Retry after 2026-04-28T10:04:16.279Z"
_RETRY_AFTER_BODY = re.compile(
    r"Retry after (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"
)


def parse_gmail_retry_after(error: Exception) -> datetime | None:
    """Extract the Retry-After timestamp from a Gmail HttpError.

    Two locations are checked in order:
    1. Header `Retry-After` (per Google's docs — usually seconds-from-now).
    2. Body substring "Retry after <iso8601>" — what the user-rate-limit
       error actually carries in practice.

    Returns None if neither is parseable.
    """
    # Header takes precedence — most rate-limit responses set it.
    headers = getattr(error, "headers", None) or {}
    if hasattr(headers, "get"):
        ra = headers.get("Retry-After") or headers.get("retry-after")
        if ra:
            try:
                seconds = int(ra)
                return datetime.now(timezone.utc).replace(microsecond=0) + _td(seconds=seconds)
            except (TypeError, ValueError):
                pass  # not seconds; fall through to ISO parse below

    # Body fallback — what the user-rate-limit error carries in practice.
    text = str(error)
    match = _RETRY_AFTER_BODY.search(text)
    if match:
        iso = match.group(1).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(iso)
        except ValueError:
            return None

    return None


def _td(*, seconds: int):
    """Lazy import to keep the module tiny + avoid circular at top."""
    from datetime import timedelta
    return timedelta(seconds=seconds)


async def is_gmail_rate_limited(integration_id: str) -> bool:
    """Return True iff the integration is currently parked on a Retry-After.

    Cheap single-row read by primary key. Auto-clears the column when the
    park has expired so subsequent calls don't pay the read again.
    """
    async with get_db_context() as db:
        row = (await db.execute(
            select(EmailIntegration).where(EmailIntegration.id == integration_id)
        )).scalar_one_or_none()
        if not row or not row.gmail_retry_after_at:
            return False
        now = datetime.now(timezone.utc)
        retry_at = row.gmail_retry_after_at
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        if now < retry_at:
            return True
        # Park expired — clear it so callers don't keep re-checking.
        row.gmail_retry_after_at = None
        await db.commit()
        return False


async def record_gmail_rate_limit(integration_id: str, retry_at: datetime) -> None:
    """Persist a Retry-After window. All Gmail paths honor it before next call."""
    async with get_db_context() as db:
        row = (await db.execute(
            select(EmailIntegration).where(EmailIntegration.id == integration_id)
        )).scalar_one_or_none()
        if not row:
            return
        # Don't reduce an existing park; only extend it. A burst of 429s
        # across paths shouldn't shrink the window.
        existing = row.gmail_retry_after_at
        if existing and existing.tzinfo is None:
            existing = existing.replace(tzinfo=timezone.utc)
        if existing is None or retry_at > existing:
            row.gmail_retry_after_at = retry_at
            await db.commit()
            logger.warning(
                f"Gmail integration {integration_id} parked until {retry_at.isoformat()}"
            )
