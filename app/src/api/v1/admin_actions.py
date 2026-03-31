"""Admin action endpoints — thin router delegating to AgentActionService."""

import json
from typing import Optional
from pydantic import BaseModel
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
    customer_id: Optional[str] = Query(None),
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
        customer_id=customer_id,
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
        job_path=body.job_path,
        line_items=[li.model_dump() for li in body.line_items] if body.line_items else None,
    )


class SendEstimateBody(BaseModel):
    to_email: Optional[str] = None  # Override recipient email


@router.post("/agent-actions/{action_id}/send-estimate")
async def send_estimate(
    action_id: str,
    body: SendEstimateBody = SendEstimateBody(),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Send estimate email to customer for a customer-path job."""
    import secrets
    from sqlalchemy import select
    from src.models.agent_action import AgentAction
    from src.models.invoice import Invoice, InvoiceLineItem
    from src.models.estimate_approval import EstimateApproval
    from src.models.customer import Customer
    from src.services.email_service import EmailService

    # Get the job
    action_result = await db.execute(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.organization_id == ctx.organization_id,
        )
    )
    action = action_result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Job not found")
    if not action.invoice_id:
        raise HTTPException(status_code=400, detail="No estimate linked to this job")

    # Get invoice + line items
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == action.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Estimate not found")

    items_result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.invoice_id == invoice.id
        ).order_by(InvoiceLineItem.sort_order)
    )
    items = items_result.scalars().all()

    # Get customer + estimate contacts
    if not invoice.customer_id:
        raise HTTPException(status_code=400, detail="No customer linked")

    cust_result = await db.execute(
        select(Customer).where(Customer.id == invoice.customer_id)
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=400, detail="Customer not found")

    # Find estimate recipients from contacts
    from src.models.customer_contact import CustomerContact
    contacts_result = await db.execute(
        select(CustomerContact).where(
            CustomerContact.customer_id == invoice.customer_id,
            CustomerContact.receives_estimates == True,
            CustomerContact.email.isnot(None),
        )
    )
    estimate_contacts = contacts_result.scalars().all()

    # Fallback to customer.email if no contacts configured
    if not body.to_email and not estimate_contacts and not customer.email:
        raise HTTPException(status_code=400, detail="No email address for this customer")

    # Create or reuse approval record with token
    existing_approval = await db.execute(
        select(EstimateApproval).where(EstimateApproval.invoice_id == invoice.id)
    )
    approval = existing_approval.scalar_one_or_none()
    if not approval:
        import uuid
        snapshot = {
            "line_items": [
                {"description": li.description, "quantity": float(li.quantity),
                 "unit_price": float(li.unit_price), "total": float(li.amount or li.quantity * li.unit_price)}
                for li in items
            ],
            "total": float(invoice.total or 0),
            "subject": invoice.subject,
        }
        approval = EstimateApproval(
            id=str(uuid.uuid4()),
            organization_id=ctx.organization_id,
            invoice_id=invoice.id,
            approved_by_type="pending",
            approved_by_name="",
            approval_token=secrets.token_urlsafe(32),
            approval_method="email_link",
            snapshot_json=json.dumps(snapshot),
        )
        db.add(approval)
        await db.flush()

    # Build approval URL
    from src.core.config import settings
    base_url = getattr(settings, "FRONTEND_URL", None) or "https://app.quantumpoolspro.com"
    approve_url = f"{base_url}/approve/{approval.approval_token}"

    # Determine recipients and store primary recipient name for signature pre-fill
    if body.to_email:
        recipients = [body.to_email]
        # Look up contact name by email
        match = next((c for c in estimate_contacts if c.email == body.to_email), None)
        approval.recipient_name = match.name if match else None
        approval.recipient_email = body.to_email
    elif estimate_contacts:
        recipients = [c.email for c in estimate_contacts]
        # Use first contact's name for pre-fill
        approval.recipient_name = estimate_contacts[0].name
        approval.recipient_email = estimate_contacts[0].email
    else:
        recipients = [customer.email]
        approval.recipient_name = f"{customer.first_name} {customer.last_name}".strip()
        approval.recipient_email = customer.email

    customer_name = f"{customer.first_name} {customer.last_name}".strip()
    email_svc = EmailService(db)

    sent_to = []
    errors = []
    for recipient in recipients:
        result = await email_svc.send_estimate_email(
            org_id=ctx.organization_id,
            to=recipient,
            customer_name=customer_name,
            estimate_number=invoice.invoice_number,
            subject=f"Estimate: {invoice.subject or 'Service Estimate'}",
            total=float(invoice.total or 0),
            view_url=approve_url,
        )
        if result.success:
            sent_to.append(recipient)
        else:
            errors.append(f"{recipient}: {result.error}")

    if not sent_to:
        raise HTTPException(status_code=500, detail=f"Failed to send: {'; '.join(errors)}")

    # Update statuses
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    invoice.status = "sent"
    invoice.sent_at = now
    action.status = "pending_approval"
    await db.commit()

    return {"sent": True, "to": sent_to, "approval_token": approval.approval_token}


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
        action_type=body.action_type,
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
