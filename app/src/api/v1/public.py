"""Public endpoints — no authentication required. Token-gated access."""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.database import get_db
from src.models.invoice import Invoice, InvoiceLineItem
from src.models.estimate_approval import EstimateApproval
from src.models.agent_action import AgentAction
from src.models.organization import Organization
from src.models.org_cost_settings import OrgCostSettings

router = APIRouter(prefix="/public", tags=["public"])


class ApproveRequest(BaseModel):
    name: str
    email: str | None = None
    signature: str | None = None
    user_agent: str | None = None
    notes: str | None = None


@router.get("/estimate/{token}")
async def view_estimate(token: str, db: AsyncSession = Depends(get_db)):
    """Public estimate view — customer clicks link from email."""
    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found or link expired")

    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == approval.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Estimate not found")

    org_result = await db.execute(
        select(Organization).where(Organization.id == invoice.organization_id)
    )
    org = org_result.scalar_one_or_none()

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

    customer_name = None
    customer_email = None
    if invoice.customer_id:
        from src.models.customer import Customer
        cust_result = await db.execute(
            select(Customer).where(Customer.id == invoice.customer_id)
        )
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_name = f"{cust.first_name} {cust.last_name}".strip()
            customer_email = cust.email

    # Get org terms settings
    settings_result = await db.execute(
        select(OrgCostSettings).where(OrgCostSettings.organization_id == invoice.organization_id)
    )
    settings = settings_result.scalar_one_or_none()

    if not invoice.viewed_at:
        invoice.viewed_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "estimate_number": invoice.invoice_number,
        "subject": invoice.subject,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "org_name": org.name if org else None,
        "org_logo_url": org.logo_url if org and hasattr(org, "logo_url") else None,
        "org_color": org.brand_color if org and hasattr(org, "brand_color") else None,
        "line_items": items,
        "total": float(invoice.total or 0),
        "recipient_name": approval.recipient_name,
        "terms": {
            "payment_terms_days": settings.payment_terms_days if settings else 30,
            "estimate_validity_days": settings.estimate_validity_days if settings else 30,
            "late_fee_pct": settings.late_fee_pct if settings else 1.5,
            "warranty_days": settings.warranty_days if settings else 30,
            "custom_terms": settings.estimate_terms if settings else None,
        },
        "status": "approved" if approval.approved_by_type and approval.approved_by_type != "pending" else "pending",
        "approved_at": approval.approved_at.isoformat() if approval.approved_by_type and approval.approved_by_type != "pending" else None,
        "approval_evidence": {
            "signed_by": approval.approved_by_name,
            "signature": approval.signature_data,
            "sent_to_email": approval.recipient_email,
            "ip_address": approval.client_ip,
            "method": approval.approval_method,
            "timestamp": approval.approved_at.isoformat() if approval.approved_at else None,
        } if approval.approved_by_type and approval.approved_by_type != "pending" else None,
        "revision_count": invoice.revision_count or 0,
        "revised_at": invoice.revised_at.isoformat() if invoice.revised_at else None,
    }


@router.post("/estimate/{token}/approve")
async def approve_estimate(
    token: str,
    body: ApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Customer approves an estimate — single step: name + typed signature + consent."""
    from src.services.estimate_workflow_service import EstimateWorkflowService
    wf = EstimateWorkflowService(db)
    result = await wf.approve_by_customer(
        token=token,
        name=body.name,
        email=body.email,
        signature=body.signature,
        user_agent=body.user_agent,
        notes=body.notes,
        client_ip=request.client.host if request.client else None,
    )
    if "error" in result:
        code = {"not_found": 404, "validation": 400}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.get("/estimate/{token}/pdf")
async def download_estimate_pdf(token: str, db: AsyncSession = Depends(get_db)):
    """Public PDF download — customer can download estimate without auth."""
    from src.models.customer import Customer
    from src.services.pdf_service import generate_invoice_pdf
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found or link expired")

    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == approval.invoice_id).options(selectinload(Invoice.line_items))
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Estimate not found")

    org_result = await db.execute(select(Organization).where(Organization.id == invoice.organization_id))
    org = org_result.scalar_one_or_none()

    customer_data = {}
    if invoice.customer_id:
        cust_result = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_data = {
                "display_name": cust.display_name,
                "company_name": cust.company_name,
                "email": cust.email,
                "billing_address": cust.billing_address,
            }

    org_data = {
        "name": org.name if org else "",
        "phone": org.phone if org else None,
        "email": org.email if org else None,
        "address": org.address if org else None,
        "city": org.city if org else None,
        "state": org.state if org else None,
        "zip_code": org.zip_code if org else None,
        "primary_color": org.primary_color if org else None,
    }

    invoice_data = {
        "invoice_number": invoice.invoice_number,
        "document_type": invoice.document_type,
        "subject": invoice.subject,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "subtotal": float(invoice.subtotal or 0),
        "discount": float(invoice.discount or 0),
        "tax_rate": float(invoice.tax_rate or 0),
        "tax_amount": float(invoice.tax_amount or 0),
        "total": float(invoice.total or 0),
        "amount_paid": float(invoice.amount_paid or 0),
        "balance": float(invoice.balance or 0),
        "notes": invoice.notes,
    }

    line_items_data = [
        {
            "description": li.description,
            "quantity": float(li.quantity),
            "unit_price": float(li.unit_price),
            "amount": float(li.amount or li.quantity * li.unit_price),
            "is_taxed": li.is_taxed if hasattr(li, "is_taxed") else False,
        }
        for li in (invoice.line_items or [])
    ]

    pdf_bytes = generate_invoice_pdf(org_data, invoice_data, customer_data, line_items_data)
    number = invoice.invoice_number or "draft"
    filename = f"estimate_{number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
