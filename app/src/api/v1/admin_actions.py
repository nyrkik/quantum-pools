"""Admin action endpoints — thin router delegating to AgentActionService."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import OrgUserContext, require_roles, OrgRole
from src.schemas.agent_action import (
    CreateActionBody,
    UpdateActionBody,
    AddCommentBody,
    CreateTaskBody,
    UpdateTaskBody,
)
from src.services.agent_action_service import AgentActionService

router = APIRouter(prefix="/admin", tags=["admin-actions"])


@router.get("/agent-actions")
async def list_agent_actions(
    status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List jobs — both email-linked and standalone."""
    service = AgentActionService(db)
    return await service.list_actions(
        org_id=ctx.organization_id,
        status=status,
        assigned_to=assigned_to,
        action_type=action_type,
        limit=limit,
    )


@router.post("/agent-actions")
async def create_agent_action(
    body: CreateActionBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create an action item — standalone or linked to a message."""
    service = AgentActionService(db)
    return await service.create_action(
        org_id=ctx.organization_id,
        action_type=body.action_type,
        description=body.description,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
        agent_message_id=body.agent_message_id,
        assigned_to=body.assigned_to,
        due_date=body.due_date,
        customer_name=body.customer_name,
        property_address=body.property_address,
    )


@router.put("/agent-actions/{action_id}")
async def update_agent_action(
    action_id: str,
    body: UpdateActionBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update an action item (status, assignment, etc)."""
    service = AgentActionService(db)
    result = await service.update_action(
        org_id=ctx.organization_id,
        action_id=action_id,
        user_id=ctx.user.id,
        user_first_name=ctx.user.first_name,
        status=body.status,
        assigned_to=body.assigned_to,
        description=body.description,
        due_date=body.due_date,
        notes=body.notes,
        invoice_id=body.invoice_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return result


@router.get("/agent-actions/{action_id}")
async def get_agent_action(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get a single action with comments and tasks."""
    service = AgentActionService(db)
    result = await service.get_action_detail(
        org_id=ctx.organization_id,
        action_id=action_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return result


@router.post("/agent-actions/{action_id}/comments")
async def add_action_comment(
    action_id: str,
    body: AddCommentBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to an action item."""
    service = AgentActionService(db)
    result = await service.add_comment(
        org_id=ctx.organization_id,
        action_id=action_id,
        author=f"{ctx.user.first_name} {ctx.user.last_name}",
        text=body.text,
        user_id=ctx.user.id,
        user_first_name=ctx.user.first_name,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return result


@router.post("/agent-actions/{action_id}/approve-suggestion")
async def approve_suggestion(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Approve a suggested action — converts it to a normal open action."""
    from sqlalchemy import select
    from src.models.agent_action import AgentAction

    result = await db.execute(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.organization_id == ctx.organization_id,
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if not action.is_suggested:
        raise HTTPException(status_code=400, detail="Action is not a suggestion")
    action.is_suggested = False
    action.suggestion_confidence = None
    await db.commit()
    return {"ok": True, "id": action.id, "is_suggested": False}


@router.post("/agent-actions/{action_id}/dismiss-suggestion")
async def dismiss_suggestion(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a suggested action — cancels it."""
    from sqlalchemy import select
    from src.models.agent_action import AgentAction

    result = await db.execute(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.organization_id == ctx.organization_id,
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if not action.is_suggested:
        raise HTTPException(status_code=400, detail="Action is not a suggestion")
    action.status = "cancelled"
    action.is_suggested = False
    action.notes = (action.notes or "") + "\nSuggestion dismissed"
    action.notes = action.notes.strip()
    await db.commit()
    return {"ok": True, "id": action.id, "status": "cancelled"}


@router.post("/agent-actions/{action_id}/draft-invoice")
async def draft_invoice_from_action(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """AI drafts invoice line items from action context (comments, description, customer)."""
    service = AgentActionService(db)
    result = await service.draft_invoice(
        org_id=ctx.organization_id,
        action_id=action_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return result


# --- Job Tasks (Sub-tasks) ---

@router.get("/agent-actions/{action_id}/tasks")
async def list_tasks(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for a job."""
    service = AgentActionService(db)
    return await service.list_tasks(
        org_id=ctx.organization_id,
        action_id=action_id,
    )


@router.post("/agent-actions/{action_id}/tasks")
async def create_task(
    action_id: str,
    body: CreateTaskBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Add a task to a job."""
    service = AgentActionService(db)
    result = await service.create_task(
        org_id=ctx.organization_id,
        action_id=action_id,
        title=body.title,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
        assigned_to=body.assigned_to,
        due_date=body.due_date,
        notes=body.notes,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.put("/agent-actions/{action_id}/tasks/{task_id}")
async def update_task(
    action_id: str,
    task_id: str,
    body: UpdateTaskBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update a task."""
    service = AgentActionService(db)
    result = await service.update_task(
        org_id=ctx.organization_id,
        action_id=action_id,
        task_id=task_id,
        user_full_name=f"{ctx.user.first_name} {ctx.user.last_name}",
        title=body.title,
        assigned_to=body.assigned_to,
        status=body.status,
        due_date=body.due_date,
        notes=body.notes,
        sort_order=body.sort_order,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/agent-actions/{action_id}/tasks/{task_id}")
async def delete_task(
    action_id: str,
    task_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task."""
    service = AgentActionService(db)
    deleted = await service.delete_task(
        org_id=ctx.organization_id,
        action_id=action_id,
        task_id=task_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
