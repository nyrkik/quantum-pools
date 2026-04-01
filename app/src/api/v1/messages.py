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
from src.models.message_attachment import MessageAttachment
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
    attachment_ids: Optional[list[str]] = None


class ReplyBody(BaseModel):
    message: str
    attachment_ids: Optional[list[str]] = None


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

    # Claim attachments
    if body.attachment_ids:
        att_ids = body.attachment_ids[:5]  # max 5
        atts = (await db.execute(
            select(MessageAttachment).where(
                MessageAttachment.id.in_(att_ids),
                MessageAttachment.organization_id == org_id,
                MessageAttachment.source_type == "internal_message",
                MessageAttachment.source_id.is_(None),
            )
        )).scalars().all()
        for att in atts:
            att.source_id = msg.id

    # Update thread
    thread.message_count = (thread.message_count or 0) + 1
    thread.last_message_at = now
    thread.last_message_by = from_user_id
    thread.status = "active"

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
    from sqlalchemy import cast, String, func, or_
    from src.models.thread_read import ThreadRead

    # Threads where user is participant and either:
    # - no read record exists, OR
    # - last_message_at > read_at
    # Exclude threads where the user sent the last message (those are always "read")
    q = (
        select(func.count(InternalThread.id))
        .outerjoin(ThreadRead, (ThreadRead.thread_id == InternalThread.id) & (ThreadRead.user_id == ctx.user.id))
        .where(
            InternalThread.organization_id == ctx.organization_id,
            cast(InternalThread.participant_ids, String).contains(ctx.user.id),
            InternalThread.last_message_by != ctx.user.id,
            or_(
                ThreadRead.read_at.is_(None),
                InternalThread.last_message_at > ThreadRead.read_at,
            ),
        )
    )
    count = (await db.execute(q)).scalar() or 0

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

    # Mark as read
    from src.models.thread_read import ThreadRead
    existing_read = (await db.execute(
        select(ThreadRead).where(ThreadRead.user_id == ctx.user.id, ThreadRead.thread_id == thread_id)
    )).scalar_one_or_none()
    if existing_read:
        existing_read.read_at = datetime.now(timezone.utc)
    else:
        db.add(ThreadRead(user_id=ctx.user.id, thread_id=thread_id))
    await db.flush()

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
            attachment_ids=body.attachment_ids,
        ),
        ctx=ctx,
        db=db,
    )


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

    await db.commit()
    return {"action_id": action.id, "converted": True}
