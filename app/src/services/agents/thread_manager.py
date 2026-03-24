"""Thread lifecycle management."""

import logging

from sqlalchemy import select, func
from src.core.database import get_db_context
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction

logger = logging.getLogger(__name__)


def _normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes for thread matching."""
    s = subject.strip()
    while True:
        lower = s.lower()
        if lower.startswith("re:"):
            s = s[3:].strip()
        elif lower.startswith("fwd:"):
            s = s[4:].strip()
        elif lower.startswith("fw:"):
            s = s[3:].strip()
        else:
            break
    return s


def _make_thread_key(contact_email: str, subject: str) -> str:
    """Create a thread key from contact email and normalized subject."""
    return f"{_normalize_subject(subject)}|{contact_email}".lower()


async def get_or_create_thread(
    contact_email: str, subject: str,
    organization_id: str = "",
    customer_id: str | None = None, customer_name: str | None = None,
    property_address: str | None = None, category: str | None = None,
    urgency: str | None = None,
) -> "AgentThread":
    """Find existing thread or create new one."""
    from src.models.agent_thread import AgentThread

    thread_key = _make_thread_key(contact_email, subject)

    async with get_db_context() as db:
        result = await db.execute(
            select(AgentThread).where(AgentThread.thread_key == thread_key)
        )
        thread = result.scalar_one_or_none()

        if not thread:
            thread = AgentThread(
                organization_id=organization_id,
                thread_key=thread_key,
                contact_email=contact_email,
                subject=subject,
                matched_customer_id=customer_id,
                customer_name=customer_name,
                property_address=property_address,
                status="pending",
                urgency=urgency,
                category=category,
                message_count=0,
            )
            db.add(thread)
            await db.commit()
            await db.refresh(thread)
        else:
            # Update customer info if we have better data now
            if customer_id and not thread.matched_customer_id:
                thread.matched_customer_id = customer_id
            if customer_name and not thread.customer_name:
                thread.customer_name = customer_name
            if property_address and not thread.property_address:
                thread.property_address = property_address
            await db.commit()

        return thread


async def update_thread_status(thread_id: str):
    """Recalculate denormalized thread fields from its messages."""
    from src.models.agent_thread import AgentThread

    async with get_db_context() as db:
        thread = (await db.execute(select(AgentThread).where(AgentThread.id == thread_id))).scalar_one_or_none()
        if not thread:
            return

        msgs = (await db.execute(
            select(AgentMessage)
            .where(AgentMessage.thread_id == thread_id)
            .order_by(AgentMessage.received_at)
        )).scalars().all()

        if not msgs:
            return

        has_pending = any(m.status == "pending" for m in msgs)
        has_sent = any(m.status in ("sent", "auto_sent") for m in msgs)

        thread.message_count = len(msgs)
        thread.has_pending = has_pending
        thread.status = "pending" if has_pending else ("handled" if has_sent else "ignored")

        last = msgs[-1]
        thread.last_message_at = last.received_at
        thread.last_direction = last.direction
        thread.last_snippet = (last.body or "")[:200]

        # Highest urgency
        prio = {"high": 3, "medium": 2, "low": 1}
        best_urg = None
        for m in msgs:
            if m.urgency and prio.get(m.urgency, 0) > prio.get(best_urg or "", 0):
                best_urg = m.urgency
        thread.urgency = best_urg

        # Latest inbound category
        for m in reversed(msgs):
            if m.direction == "inbound" and m.category:
                thread.category = m.category
                break

        # Check open actions
        action_result = await db.execute(
            select(func.count(AgentAction.id)).where(
                AgentAction.thread_id == thread_id,
                AgentAction.status.in_(("open", "in_progress")),
            )
        )
        thread.has_open_actions = (action_result.scalar() or 0) > 0

        await db.commit()


async def _get_thread_open_actions(thread_id: str) -> list[str]:
    """Get descriptions of open action items for a thread."""
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentAction)
            .where(
                AgentAction.thread_id == thread_id,
                AgentAction.status.in_(("open", "in_progress")),
            )
        )
        return [a.description for a in result.scalars().all()]
