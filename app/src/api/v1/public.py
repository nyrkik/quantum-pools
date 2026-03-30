"""Public endpoints — no authentication required. Token-gated access."""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.database import get_db
from src.models.invoice import Invoice, InvoiceLineItem
from src.models.estimate_approval import EstimateApproval
from src.models.agent_action import AgentAction
from src.models.organization import Organization

router = APIRouter(prefix="/public", tags=["public"])


class ApprovalResponse(BaseModel):
    estimate_number: str
    subject: str | None
    customer_name: str | None
    org_name: str | None
    org_logo_url: str | None
    org_color: str | None
    line_items: list[dict]
    total: float
    status: str
    approved_at: str | None = None


class ApproveRequest(BaseModel):
    name: str
    email: str | None = None
    notes: str | None = None


@router.get("/estimate/{token}")
async def view_estimate(token: str, db: AsyncSession = Depends(get_db)):
    """Public estimate view — customer clicks link from email."""
    # Find approval record by token
    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found or link expired")

    # Get invoice
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == approval.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Estimate not found")

    # Get org info for branding
    org_result = await db.execute(
        select(Organization).where(Organization.id == invoice.organization_id)
    )
    org = org_result.scalar_one_or_none()

    # Get line items
    items_result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.invoice_id == invoice.id
        ).order_by(InvoiceLineItem.sort_order)
    )
    items = [
        {
            "description": li.description,
            "quantity": float(li.quantity),
            "unit_price": float(li.unit_price),
            "total": float(li.total),
        }
        for li in items_result.scalars().all()
    ]

    # Get customer name
    customer_name = None
    if invoice.customer_id:
        from src.models.customer import Customer
        cust_result = await db.execute(
            select(Customer).where(Customer.id == invoice.customer_id)
        )
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_name = f"{cust.first_name} {cust.last_name}".strip()

    # Mark as viewed
    if not invoice.viewed_at:
        invoice.viewed_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "estimate_number": invoice.invoice_number,
        "subject": invoice.subject,
        "customer_name": customer_name,
        "org_name": org.name if org else None,
        "org_logo_url": org.logo_url if org and hasattr(org, "logo_url") else None,
        "org_color": org.brand_color if org and hasattr(org, "brand_color") else None,
        "line_items": items,
        "total": float(invoice.total or 0),
        "status": "approved" if approval.approved_at else "pending",
        "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
    }


@router.post("/estimate/{token}/approve")
async def approve_estimate(
    token: str,
    body: ApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Customer approves an estimate via email link."""
    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found or link expired")

    if approval.approved_at:
        return {"already_approved": True, "approved_at": approval.approved_at.isoformat()}

    # Record approval
    now = datetime.now(timezone.utc)
    approval.approved_at = now
    approval.approved_by_type = "client"
    approval.approved_by_name = body.name
    approval.client_email = body.email
    approval.client_ip = request.client.host if request.client else None
    approval.approval_method = "email_link"
    approval.notes = body.notes

    # Update invoice
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == approval.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if invoice:
        invoice.approved_at = now
        invoice.approved_by = body.name
        invoice.status = "approved"

        # Update linked job status
        action_result = await db.execute(
            select(AgentAction).where(
                AgentAction.invoice_id == invoice.id,
                AgentAction.status == "pending_approval",
            )
        )
        action = action_result.scalar_one_or_none()
        if action:
            action.status = "approved"

    await db.commit()

    return {"approved": True, "approved_at": now.isoformat()}
