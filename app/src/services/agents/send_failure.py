"""Shared helper for recording outbound send failures.

Every path that sends customer email — compose, reply approval, follow-up,
auto-send — needs the same crash handling: rollback the transaction, persist
a `failed` outbound AgentMessage with the actual error in `delivery_error`,
and recompute thread state. Without this, a crash mid-send leaves the message
in an indeterminate state with no record visible to the user.

This module exists so the recovery is consistent everywhere — the FB-24
incident showed that fixing one path while leaving four others vulnerable
just relocates the bug.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_message import AgentMessage

logger = logging.getLogger(__name__)


async def record_outbound_send_failure(
    db: AsyncSession,
    *,
    org_id: str,
    thread_id: str | None,
    from_email: str,
    to_email: str,
    subject: str | None,
    body: str,
    error: str,
    matched_customer_id: str | None = None,
    customer_name: str | None = None,
) -> None:
    """Persist a failed outbound AgentMessage so the failure is visible in the
    Failed filter and on the thread timeline. Recomputes thread state.

    Best-effort: never raises. Designed for use inside an `except` block where
    the caller has already lost their primary transaction.

    `error` is captured into `delivery_error` (truncated to 500 chars).
    """
    from src.services.agents.thread_manager import update_thread_status

    try:
        # Roll back any partial work from the crashed transaction so we can
        # commit the failed-message row cleanly.
        try:
            await db.rollback()
        except Exception:
            pass

        now = datetime.now(timezone.utc)
        failed = AgentMessage(
            organization_id=org_id,
            direction="outbound",
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            body=body,
            status="failed",
            delivery_error=(error or "unknown send error")[:500],
            thread_id=thread_id,
            matched_customer_id=matched_customer_id,
            customer_name=customer_name,
            received_at=now,
        )
        db.add(failed)
        await db.commit()
        if thread_id:
            await update_thread_status(thread_id)
    except Exception as inner:
        logger.error(
            f"record_outbound_send_failure failed (org={org_id} thread={thread_id}): {inner}"
        )
