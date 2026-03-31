"""Admin thread endpoints — thin router delegating to AgentThreadService.

Access: owner, admin, manager (visibility filtering replaces hard role gating).
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import OrgUserContext, require_roles, OrgRole
from src.schemas.agent_thread import ApproveBody, ReviseDraftBody, AssignThreadBody
from src.services.agent_thread_service import AgentThreadService

router = APIRouter(prefix="/admin", tags=["admin-threads"])


async def _get_user_perm_slugs(ctx: OrgUserContext, db: AsyncSession) -> set[str]:
    """Load user's permission slugs for visibility filtering."""
    perms = await ctx.load_permissions(db)
    return set(perms.keys())


@router.get("/client-search")
async def search_clients(
    q: str = Query(..., min_length=2),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Search customers + properties for autocomplete."""
    service = AgentThreadService(db)
    return await service.search_clients(org_id=ctx.organization_id, q=q)


@router.get("/agent-threads")
async def list_threads(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    exclude_spam: bool = Query(True),
    exclude_ignored: bool = Query(False),
    assigned_to: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """List conversation threads (visibility-filtered by user permissions)."""
    perm_slugs = await _get_user_perm_slugs(ctx, db)
    service = AgentThreadService(db)
    return await service.list_threads(
        org_id=ctx.organization_id,
        status=status,
        search=search,
        exclude_spam=exclude_spam,
        exclude_ignored=exclude_ignored,
        limit=limit,
        offset=offset,
        assigned_to=assigned_to,
        customer_id=customer_id,
        current_user_id=ctx.user.id,
        user_permission_slugs=perm_slugs,
    )


@router.get("/agent-threads/stats")
async def get_thread_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Thread-level stats (visibility-filtered)."""
    perm_slugs = await _get_user_perm_slugs(ctx, db)
    service = AgentThreadService(db)
    return await service.get_thread_stats(org_id=ctx.organization_id, user_permission_slugs=perm_slugs)


@router.get("/agent-threads/{thread_id}")
async def get_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Get thread with full conversation timeline. Marks as read for current user."""
    perm_slugs = await _get_user_perm_slugs(ctx, db)
    service = AgentThreadService(db)
    result = await service.get_thread_detail(org_id=ctx.organization_id, thread_id=thread_id, user_permission_slugs=perm_slugs)
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Mark as read when viewing
    await service.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id)
    return result


@router.post("/agent-threads/{thread_id}/approve")
async def approve_thread(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Approve the latest pending message in a thread."""
    service = AgentThreadService(db)
    result = await service.approve_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        response_text=body.response_text,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    if "error" in result:
        code = {"no_pending": 400, "no_text": 400, "send_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/dismiss")
async def dismiss_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss all pending messages in a thread."""
    service = AgentThreadService(db)
    return await service.dismiss_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
    )


@router.post("/agent-threads/{thread_id}/archive")
async def archive_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Archive a thread — hidden from inbox, preserved for records."""
    service = AgentThreadService(db)
    return await service.archive_thread(org_id=ctx.organization_id, thread_id=thread_id)


@router.delete("/agent-threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a thread and all messages. Owner only."""
    service = AgentThreadService(db)
    return await service.delete_thread(org_id=ctx.organization_id, thread_id=thread_id)


@router.post("/agent-threads/{thread_id}/assign")
async def assign_thread(
    thread_id: str,
    body: AssignThreadBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Assign or unassign a thread to a team member."""
    service = AgentThreadService(db)
    result = await service.assign_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        user_id=body.user_id,
        user_name=body.user_name,
    )
    if "error" in result:
        code = {"not_found": 404, "forbidden": 403}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/save-draft")
async def save_thread_draft(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Save edited draft without sending."""
    from sqlalchemy import select, desc
    from src.models.agent_message import AgentMessage
    result = await db.execute(
        select(AgentMessage)
        .where(
            AgentMessage.thread_id == thread_id,
            AgentMessage.organization_id == ctx.organization_id,
            AgentMessage.status == "pending",
            AgentMessage.direction == "inbound",
        )
        .order_by(desc(AgentMessage.received_at))
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="No pending message in this thread")
    msg.draft_response = body.response_text
    await db.commit()
    return {"saved": True}


@router.post("/agent-threads/{thread_id}/send-followup")
async def send_thread_followup(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up in a thread."""
    service = AgentThreadService(db)
    result = await service.send_followup(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        text=body.response_text or "",
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    if "error" in result:
        code = {"not_found": 404, "no_text": 400, "send_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/revise-draft")
async def revise_thread_draft(
    thread_id: str,
    body: ReviseDraftBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Revise the draft on the latest pending message in a thread."""
    service = AgentThreadService(db)
    result = await service.revise_draft(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        draft=body.draft,
        instruction=body.instruction,
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/draft-followup")
async def draft_thread_followup(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Draft a follow-up for a thread using full conversation context."""
    service = AgentThreadService(db)
    result = await service.draft_followup(
        org_id=ctx.organization_id,
        thread_id=thread_id,
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


# ── Thread visibility override ─────────────────────────────────────

class VisibilityBody(BaseModel):
    visibility_permission: Optional[str] = None


@router.patch("/agent-threads/{thread_id}/visibility")
async def update_thread_visibility(
    thread_id: str,
    body: VisibilityBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Admin override: change thread visibility permission."""
    service = AgentThreadService(db)
    result = await service.update_visibility(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        visibility_permission=body.visibility_permission,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/create-job")
async def create_job_from_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """AI creates a job from thread conversation context."""
    service = AgentThreadService(db)
    result = await service.create_job_from_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}.get(result["error"], 400)
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/draft-estimate")
async def draft_estimate_from_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """AI drafts an estimate from thread conversation context."""
    service = AgentThreadService(db)
    result = await service.draft_estimate_from_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}.get(result["error"], 400)
        raise HTTPException(status_code=code, detail=result["detail"])
    return result
