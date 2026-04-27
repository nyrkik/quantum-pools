"""Promise tracker API.

Surfaces threads where the customer made a follow-up promise and went
silent past the agreed window. The orchestrator's
`_is_followup_promise` regex sets `agent_threads.awaiting_reply_until`
on inbound; subsequent inbound clears it.

Two endpoints:
  GET  /v1/inbox/awaiting-reply           — list current awaits
  PUT  /v1/admin/agent-threads/{id}/awaiting-reply  — manual snooze/clear

Both gated by `inbox.manage`. See `docs/promise-tracker-spec.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import OrgUserContext, require_permissions
from src.core.database import get_db
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer


inbox_router = APIRouter(prefix="/inbox", tags=["inbox"])
admin_threads_router = APIRouter(prefix="/admin", tags=["admin"])


@inbox_router.get("/awaiting-reply")
async def list_awaiting_reply(
    ctx: OrgUserContext = Depends(require_permissions("inbox.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Threads where the customer promised a follow-up. `is_overdue=true`
    when `awaiting_reply_until <= NOW()` — that's what the dashboard
    widget surfaces."""
    rows = (await db.execute(
        select(AgentThread, Customer)
        .outerjoin(Customer, Customer.id == AgentThread.matched_customer_id)
        .where(
            AgentThread.organization_id == ctx.organization_id,
            AgentThread.awaiting_reply_until.is_not(None),
            AgentThread.is_historical.is_(False),
        )
        .order_by(AgentThread.awaiting_reply_until.asc())
        .limit(50)
    )).all()
    now = datetime.now(timezone.utc)

    items = []
    overdue_count = 0
    for thread, customer in rows:
        is_overdue = thread.awaiting_reply_until <= now
        if is_overdue:
            overdue_count += 1

        # Last inbound snippet (the promise itself, when possible)
        last_inbound = (await db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.thread_id == thread.id,
                AgentMessage.direction == "inbound",
            )
            .order_by(desc(AgentMessage.received_at))
            .limit(1)
        )).scalar_one_or_none()
        snippet = (last_inbound.body or "")[:200] if last_inbound else None

        customer_name = None
        if customer:
            customer_name = customer.company_name or (
                f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                or None
            )

        items.append({
            "thread_id": thread.id,
            "subject": thread.subject,
            "contact_email": thread.contact_email,
            "customer_id": thread.matched_customer_id,
            "customer_name": customer_name,
            "awaiting_reply_until": thread.awaiting_reply_until.isoformat(),
            "is_overdue": is_overdue,
            "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
            "last_inbound_snippet": snippet,
        })

    return {"items": items, "overdue_count": overdue_count, "total": len(items)}


class AwaitingReplyBody(BaseModel):
    until: datetime | None = None


@admin_threads_router.put("/agent-threads/{thread_id}/awaiting-reply")
async def set_awaiting_reply(
    thread_id: str,
    body: AwaitingReplyBody,
    ctx: OrgUserContext = Depends(require_permissions("inbox.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manual override. body={until: <iso>} snoozes/extends; body={until: null}
    clears (= "resolved, no reply needed"). Idempotent."""
    thread = await db.get(AgentThread, thread_id)
    if thread is None or thread.organization_id != ctx.organization_id:
        raise HTTPException(404, "thread not found")
    thread.awaiting_reply_until = body.until
    await db.commit()
    return {
        "thread_id": thread.id,
        "awaiting_reply_until": (
            thread.awaiting_reply_until.isoformat()
            if thread.awaiting_reply_until else None
        ),
    }
