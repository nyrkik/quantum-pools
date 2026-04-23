"""Proposal creator: `email_reply` entity_type.

Used by the Phase 5 email_drafter migration. Where `customer_email`
represents a fresh outbound email (DeepBlue's `draft_customer_email`
tool), `email_reply` represents a reply to an existing inbound
`AgentMessage` on an `AgentThread`.

Accepting the proposal:
1. Sends the reply via `EmailService.send_agent_reply` (canonical
   outbound-customer-email path — signature, from-name, Postmark/Gmail
   routing all handled there).
2. Creates an outbound `AgentMessage` row on the thread.
3. Marks the inbound message that was being replied to as `sent`
   (matches `thread_action_service.approve_thread` semantics).
4. Recomputes thread status via `update_thread_status`.

Steps 2-4 are atomic inside `ProposalService.accept`'s transaction. If
`send_agent_reply` raises the whole thing rolls back, the proposal
stays `staged`, and the user can retry.

DNA rule 5 — AI never commits to the customer — is enforced structurally
by the proposal boundary: the draft can't leave QP until a human
accepts.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.user import User
from src.services.email_service import EmailService
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


class EmailReplyProposalPayload(BaseModel):
    thread_id: str
    reply_to_message_id: str
    to: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    cc: Optional[list[str]] = None
    customer_id: Optional[str] = None


async def _resolve_sender_name(db: AsyncSession, actor: Actor) -> Optional[str]:
    """Turn the accept-time actor into a display name for signature use.
    `actor.user_id` is set for human accepts; agent accepts (rare for
    email_reply since DNA rule 5 forbids AI auto-send) return None
    and fall through to EmailService's own sender resolution.
    """
    if not getattr(actor, "user_id", None):
        return None
    u = await db.get(User, actor.user_id)
    if u is None:
        return None
    parts = [p for p in (u.first_name, u.last_name) if p]
    return " ".join(parts) if parts else None


@register("email_reply", schema=EmailReplyProposalPayload)
async def create_email_reply_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    # Defense-in-depth: proposal is already org-scoped, but re-verify
    # the thread and inbound message belong to this org. Catches stale
    # proposals where the underlying thread was deleted or moved.
    thread = (await db.execute(
        select(AgentThread).where(
            AgentThread.id == payload["thread_id"],
            AgentThread.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if thread is None:
        raise NotFoundError(f"Thread {payload['thread_id']} not in org {org_id}")

    inbound = (await db.execute(
        select(AgentMessage).where(
            AgentMessage.id == payload["reply_to_message_id"],
            AgentMessage.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if inbound is None:
        raise NotFoundError(
            f"Inbound message {payload['reply_to_message_id']} not in org {org_id}"
        )

    user_name = await _resolve_sender_name(db, actor)

    # Delegate the actual send to the canonical path. `from_address`
    # defaults to the thread's `delivered_to` (preserves per-alias
    # identity — customer emailed contact@, reply goes from contact@).
    email_svc = EmailService(db)
    cc_str: Optional[str] = None
    if payload.get("cc"):
        cc_str = ",".join(payload["cc"])

    result = await email_svc.send_agent_reply(
        org_id=org_id,
        to=payload["to"],
        subject=payload["subject"],
        body_text=payload["body"],
        from_address=thread.delivered_to,
        sender_name=user_name,
        cc=cc_str,
    )
    if not result.success:
        raise Exception(result.error or "Email send failed")

    # Bookkeeping mirrors thread_action_service.approve_thread — outbound
    # AgentMessage + inbound status update + thread_status recompute.
    now = datetime.now(timezone.utc)
    agent_from_email = os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com")
    outbound_subject = payload["subject"]
    if inbound.subject and not inbound.subject.startswith("Re:"):
        # Keep approve_thread parity — Re: prefix added at send time by
        # EmailService for non-is_new replies, but our stored subject
        # should carry it too so the thread reads sanely.
        outbound_subject = inbound.subject if inbound.subject.startswith("Re:") else f"Re: {inbound.subject}"

    inbound.status = "sent"
    inbound.final_response = payload["body"]
    inbound.approved_by = user_name
    inbound.approved_at = now
    inbound.sent_at = now

    outbound = AgentMessage(
        organization_id=org_id,
        direction="outbound",
        from_email=thread.delivered_to or agent_from_email,
        to_email=payload["to"],
        subject=outbound_subject,
        body=payload["body"],
        status="sent",
        thread_id=payload["thread_id"],
        matched_customer_id=inbound.matched_customer_id,
        customer_name=inbound.customer_name,
        approved_by=user_name,
        approved_at=now,
        sent_at=now,
        received_at=now,
    )
    db.add(outbound)
    await db.flush()

    # Recompute thread rollups (status, unread, pending flags, etc.).
    from src.services.agents.thread_manager import update_thread_status
    await update_thread_status(payload["thread_id"])

    return outbound
