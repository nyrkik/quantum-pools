"""Notification endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/count")
async def get_unread_count(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    count = (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.organization_id == ctx.organization_id,
            Notification.user_id == ctx.user.id,
            Notification.is_read == False,
        )
    )).scalar() or 0
    rv = ctx.org_user.role_version or 0
    pv = ctx.org_user.permission_version or 0
    return {"unread": count, "role_version": rv + pv}


@router.get("")
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.organization_id == ctx.organization_id, Notification.user_id == ctx.user.id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in result.scalars().all()
    ]


@router.post("/read-all")
async def mark_all_read(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.organization_id == ctx.organization_id, Notification.user_id == ctx.user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == ctx.organization_id,
            Notification.user_id == ctx.user.id,
        )
    )
    n = result.scalar_one_or_none()
    if n:
        n.is_read = True
        await db.commit()
    return {"ok": True}
