"""Internal messaging — team-to-team chat with work context."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.models.internal_message import InternalThread, InternalMessage
from src.models.notification import Notification
from src.models.user import User
from src.presenters.message_presenter import MessagePresenter

router = APIRouter(prefix="/messages", tags=["messages"])


class SendMessageBody(BaseModel):
    to_user_id: Optional[str] = None  # single recipient (backward compat)
    to_user_ids: Optional[list[str]] = None  # multiple recipients (group chat)
    message: str
    subject: Optional[str] = None
    priority: str = "normal"
    customer_id: Optional[str] = None
    property_id: Optional[str] = None
    action_id: Optional[str] = None
    thread_id: Optional[str] = None  # reply to existing thread


class ReplyBody(BaseModel):
    message: str


@router.post("", status_code=201)
async def send_message(
    body: SendMessageBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message — creates thread if new, appends if reply."""
    org_id = ctx.organization_id
    from_user_id = ctx.user.id
    now = datetime.now(timezone.utc)

    # Resolve recipients
    recipient_ids = body.to_user_ids or ([body.to_user_id] if body.to_user_id else [])

    if body.thread_id:
        # Reply to existing thread
        thread_result = await db.execute(
            select(InternalThread).where(
                InternalThread.id == body.thread_id,
                InternalThread.organization_id == org_id,
            )
        )
        thread = thread_result.scalar_one_or_none()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
    else:
        if not recipient_ids:
            raise HTTPException(status_code=400, detail="At least one recipient required")
        # Create new thread
        participants = sorted(set([from_user_id] + recipient_ids))
        thread = InternalThread(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            created_by_user_id=from_user_id,
            participant_ids=participants,
            subject=body.subject,
            priority=body.priority,
            customer_id=body.customer_id,
            property_id=body.property_id,
            action_id=body.action_id,
        )
        db.add(thread)
        await db.flush()

    # Add message
    msg = InternalMessage(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        from_user_id=from_user_id,
        text=body.message.strip(),
    )
    db.add(msg)

    # Update thread
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = now
    thread.last_message_by = from_user_id
    if thread.status in ("acknowledged", "completed"):
        thread.status = "active"  # Reopen on new message

    # Notify recipient(s)
    from_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    for pid in (thread.participant_ids or []):
        if pid != from_user_id:
            notif_type = "internal_message_urgent" if body.priority == "urgent" else "internal_message"
            db.add(Notification(
                organization_id=org_id,
                user_id=pid,
                type=notif_type,
                title=f"{'URGENT: ' if body.priority == 'urgent' else ''}{from_name}",
                body=body.message[:100],
                link=f"/messages?thread={thread.id}",
            ))

    await db.commit()
    presenter = MessagePresenter(db)
    return await presenter.thread_detail(thread, from_user_id)


@router.get("")
async def list_threads(
    view: str = Query("mine"),  # mine or team (admin only)
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List message threads. 'mine' = participant threads, 'team' = all org threads (admin/owner only)."""
    from sqlalchemy import cast, String
    from src.models.organization_user import OrganizationUser

    q = select(InternalThread).where(
        InternalThread.organization_id == ctx.organization_id,
    ).order_by(desc(InternalThread.last_message_at)).limit(limit)

    if view == "team":
        # Admin/owner only — show all org threads
        ou = (await db.execute(
            select(OrganizationUser).where(
                OrganizationUser.user_id == ctx.user.id,
                OrganizationUser.organization_id == ctx.organization_id,
            )
        )).scalar_one_or_none()
        if not ou or ou.role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Admin access required")
    else:
        # Default — only threads where user is a participant
        q = q.where(cast(InternalThread.participant_ids, String).contains(ctx.user.id))

    if status:
        q = q.where(InternalThread.status == status)

    result = await db.execute(q)
    threads = result.scalars().all()

    presenter = MessagePresenter(db)
    items = await presenter.many_threads(list(threads), ctx.user.id)
    return {"items": items, "total": len(items)}


@router.get("/stats")
async def message_stats(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Unread message count for badge."""
    from sqlalchemy import cast, String, func

    # Threads where user is participant, status=active, last_message_by != user
    count = (await db.execute(
        select(func.count(InternalThread.id)).where(
            InternalThread.organization_id == ctx.organization_id,
            cast(InternalThread.participant_ids, String).contains(ctx.user.id),
            InternalThread.status == "active",
            InternalThread.last_message_by != ctx.user.id,
        )
    )).scalar() or 0

    return {"unread": count}


@router.get("/{thread_id}")
async def get_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InternalThread).where(
            InternalThread.id == thread_id,
            InternalThread.organization_id == ctx.organization_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    presenter = MessagePresenter(db)
    return await presenter.thread_detail(thread, ctx.user.id)


@router.post("/{thread_id}/reply")
async def reply_to_thread(
    thread_id: str,
    body: ReplyBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a message to an existing thread."""
    return await send_message(
        SendMessageBody(
            to_user_id="",  # not used for replies
            message=body.message,
            thread_id=thread_id,
        ),
        ctx=ctx,
        db=db,
    )


@router.put("/{thread_id}/acknowledge")
async def acknowledge_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InternalThread).where(
            InternalThread.id == thread_id,
            InternalThread.organization_id == ctx.organization_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    now = datetime.now(timezone.utc)
    thread.status = "acknowledged"
    thread.acknowledged_at = now
    thread.acknowledged_by = ctx.user.id

    # Notify sender
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    if thread.created_by_user_id and thread.created_by_user_id != ctx.user.id:
        db.add(Notification(
            organization_id=ctx.organization_id,
            user_id=thread.created_by_user_id,
            type="message_acknowledged",
            title=f"{user_name} acknowledged your message",
            body=(thread.subject or "")[:100],
            link=f"/messages?thread={thread_id}",
        ))

    await db.commit()
    return {"status": "acknowledged"}


@router.put("/{thread_id}/complete")
async def complete_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InternalThread).where(
            InternalThread.id == thread_id,
            InternalThread.organization_id == ctx.organization_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    now = datetime.now(timezone.utc)
    thread.status = "completed"
    thread.completed_at = now
    thread.completed_by = ctx.user.id

    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    if thread.created_by_user_id and thread.created_by_user_id != ctx.user.id:
        db.add(Notification(
            organization_id=ctx.organization_id,
            user_id=thread.created_by_user_id,
            type="message_completed",
            title=f"{user_name} completed: {(thread.subject or 'message')[:50]}",
            body="",
            link=f"/messages?thread={thread_id}",
        ))

    await db.commit()
    return {"status": "completed"}


@router.post("/{thread_id}/convert-to-job")
async def convert_to_job(
    thread_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Convert a message thread into a job (AgentAction)."""
    from src.models.agent_action import AgentAction

    result = await db.execute(
        select(InternalThread).where(
            InternalThread.id == thread_id,
            InternalThread.organization_id == ctx.organization_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.converted_to_action_id:
        return {"already_converted": True, "action_id": thread.converted_to_action_id}

    # Get all messages for description
    msgs = (await db.execute(
        select(InternalMessage).where(InternalMessage.thread_id == thread_id)
        .order_by(InternalMessage.created_at)
    )).scalars().all()

    description = thread.subject or msgs[0].text[:100] if msgs else "Converted from message"

    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    action = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        action_type="follow_up",
        description=description,
        customer_id=thread.customer_id,
        status="open",
        created_by=user_name,
    )
    db.add(action)
    await db.flush()

    thread.converted_to_action_id = action.id
    thread.status = "completed"
    thread.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return {"action_id": action.id, "converted": True}
