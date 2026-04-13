"""Inbox folder management — list, create, update, delete, move threads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_org_user, get_db, OrgUserContext

router = APIRouter(prefix="/inbox-folders", tags=["inbox-folders"])


@router.get("")
async def list_folders(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.services.inbox_folder_service import InboxFolderService
    svc = InboxFolderService(db)
    folders = await svc.list_folders(ctx.organization_id, user_id=ctx.user.id)
    return {"folders": folders}


class CreateFolderBody(BaseModel):
    name: str
    icon: str | None = None
    color: str | None = None


@router.post("")
async def create_folder(
    body: CreateFolderBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owner or admin can create folders")
    from src.services.inbox_folder_service import InboxFolderService
    svc = InboxFolderService(db)
    folder = await svc.create_folder(ctx.organization_id, body.name, body.icon, body.color)
    return folder


class UpdateFolderBody(BaseModel):
    name: str | None = None
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None


@router.put("/{folder_id}")
async def update_folder(
    folder_id: str,
    body: UpdateFolderBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owner or admin can edit folders")
    from src.services.inbox_folder_service import InboxFolderService
    svc = InboxFolderService(db)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await svc.update_folder(ctx.organization_id, folder_id, **updates)
    if not result:
        raise HTTPException(404, "Folder not found")
    return result


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owner or admin can delete folders")
    from src.services.inbox_folder_service import InboxFolderService
    svc = InboxFolderService(db)
    ok = await svc.delete_folder(ctx.organization_id, folder_id)
    if not ok:
        raise HTTPException(400, "Cannot delete system folder or folder not found")
    return {"ok": True}


class MoveThreadBody(BaseModel):
    thread_id: str
    folder_id: str | None = None  # null = Inbox


@router.post("/move-thread")
async def move_thread(
    body: MoveThreadBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if ctx.role not in ("owner", "admin", "manager"):
        raise HTTPException(403, "Only owner, admin, or manager can move threads")
    from src.services.inbox_folder_service import InboxFolderService
    svc = InboxFolderService(db)
    ok = await svc.move_thread(ctx.organization_id, body.thread_id, body.folder_id)
    if not ok:
        raise HTTPException(404, "Thread or folder not found")
    return {"ok": True}


class MoveSenderBody(BaseModel):
    sender_email: str
    folder_id: str | None = None


@router.post("/move-sender")
async def move_sender(
    body: MoveSenderBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Move ALL threads from a sender to a folder."""
    if ctx.role not in ("owner", "admin", "manager"):
        raise HTTPException(403, "Only owner, admin, or manager can move threads")
    from sqlalchemy import func
    from src.models.agent_thread import AgentThread
    result = await db.execute(
        AgentThread.__table__.update()
        .where(
            AgentThread.organization_id == ctx.organization_id,
            func.lower(AgentThread.contact_email) == body.sender_email.lower().strip(),
        )
        .values(folder_id=body.folder_id, folder_override=True)
    )
    await db.commit()
    return {"ok": True, "moved": result.rowcount}
