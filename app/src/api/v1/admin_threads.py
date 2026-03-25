"""Admin thread endpoints — thin router delegating to AgentThreadService."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import OrgUserContext, require_roles, OrgRole
from src.schemas.agent_thread import ApproveBody, ReviseDraftBody
from src.services.agent_thread_service import AgentThreadService

router = APIRouter(prefix="/admin", tags=["admin-threads"])


@router.get("/client-search")
async def search_clients(
    q: str = Query(..., min_length=2),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
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
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List conversation threads."""
    service = AgentThreadService(db)
    return await service.list_threads(
        org_id=ctx.organization_id,
        status=status,
        search=search,
        exclude_spam=exclude_spam,
        exclude_ignored=exclude_ignored,
        limit=limit,
        offset=offset,
    )


@router.get("/agent-threads/stats")
async def get_thread_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Thread-level stats."""
    service = AgentThreadService(db)
    return await service.get_thread_stats(org_id=ctx.organization_id)


@router.get("/agent-threads/{thread_id}")
async def get_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get thread with full conversation timeline."""
    service = AgentThreadService(db)
    result = await service.get_thread_detail(org_id=ctx.organization_id, thread_id=thread_id)
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    return result


@router.post("/agent-threads/{thread_id}/approve")
async def approve_thread(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
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
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss all pending messages in a thread."""
    service = AgentThreadService(db)
    return await service.dismiss_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
    )


@router.post("/agent-threads/{thread_id}/send-followup")
async def send_thread_followup(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
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
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
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
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
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
