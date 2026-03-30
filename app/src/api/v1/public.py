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


class SendCodeRequest(BaseModel):
    email: str


class ApproveRequest(BaseModel):
    name: str
    email: str | None = None
    signature: str | None = None
    verification_code: str | None = None
    user_agent: str | None = None
    notes: str | None = None


# In-memory code store (short-lived, per-token)
_verification_codes: dict[str, tuple[str, datetime]] = {}


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
            "total": float(li.amount or li.quantity * li.unit_price),
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
        "customer_email": cust.email if cust else None,
        "status": "approved" if approval.approved_by_type and approval.approved_by_type != "pending" else "pending",
        "approved_at": approval.approved_at.isoformat() if approval.approved_by_type and approval.approved_by_type != "pending" else None,
    }


@router.post("/estimate/{token}/send-code")
async def send_verification_code(
    token: str,
    body: SendCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a 6-digit verification code to the customer's email."""
    import random

    # Verify token exists
    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found")

    # Generate 6-digit code
    code = f"{random.randint(100000, 999999)}"
    _verification_codes[token] = (code, datetime.now(timezone.utc))

    # Get org for branding
    invoice_result = await db.execute(select(Invoice).where(Invoice.id == approval.invoice_id))
    invoice = invoice_result.scalar_one_or_none()

    # Send email with code
    from src.services.email_service import EmailService
    email_svc = EmailService(db)
    org_id = approval.organization_id
    await email_svc.send_email(
        org_id=org_id,
        to=body.email,
        subject="Your verification code",
        body=f"Your verification code is: {code}\n\nEnter this code to approve estimate {invoice.invoice_number if invoice else ''}.\n\nThis code expires in 15 minutes.",
    )

    return {"sent": True}


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

    if approval.approved_by_type and approval.approved_by_type != "pending":
        return {"already_approved": True, "approved_at": approval.approved_at.isoformat()}

    # Verify code
    from datetime import timedelta
    stored = _verification_codes.get(token)
    if not stored:
        raise HTTPException(status_code=400, detail="Verification code expired. Please request a new code.")
    stored_code, stored_at = stored
    if datetime.now(timezone.utc) - stored_at > timedelta(minutes=15):
        del _verification_codes[token]
        raise HTTPException(status_code=400, detail="Verification code expired. Please request a new code.")
    if body.verification_code != stored_code:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please check and try again.")
    del _verification_codes[token]

    # Record approval
    now = datetime.now(timezone.utc)
    approval.approved_at = now
    approval.approved_by_type = "client"
    approval.approved_by_name = body.name
    approval.client_email = body.email
    approval.client_ip = request.client.host if request.client else None
    approval.approval_method = "email_link"
    approval.signature_data = body.signature
    approval.notes = f"User-Agent: {body.user_agent or 'unknown'}" + (f"\n{body.notes}" if body.notes else "")

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
