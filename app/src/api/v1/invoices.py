"""Invoice endpoints — all org-scoped."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import NotFoundError, ValidationError
from src.api.deps import get_current_org_user, require_feature, OrgUserContext
from src.schemas.invoice import InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceLineItemResponse, InvoiceStatsResponse
from src.services.invoice_service import InvoiceService, log_job_activity

router = APIRouter(prefix="/invoices", tags=["invoices"], dependencies=[Depends(require_feature("invoicing"))])


from src.presenters.invoice_presenter import InvoicePresenter

def _invoice_to_response(invoice) -> dict:
    """Present invoice via InvoicePresenter (sync — customer already loaded via relationship)."""
    return InvoicePresenter(None)._serialize(invoice)


@router.get("", response_model=dict)
async def list_invoices(
    status: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoices, total = await svc.list(
        ctx.organization_id, status=status, customer_id=customer_id,
        date_from=date_from, date_to=date_to, search=search,
        skip=skip, limit=limit, document_type=document_type,
    )
    results = [_invoice_to_response(inv) for inv in invoices]
    return {"items": results, "total": total}


@router.post("", status_code=201)
async def create_invoice(
    body: InvoiceCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    line_items_data = [item.model_dump() for item in body.line_items]
    invoice = await svc.create(
        ctx.organization_id,
        customer_id=body.customer_id,
        line_items_data=line_items_data,
        document_type=body.document_type,
        subject=body.subject,
        issue_date=body.issue_date,
        due_date=body.due_date,
        discount=body.discount,
        tax_rate=body.tax_rate,
        is_recurring=body.is_recurring,
        notes=body.notes,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip(),
    )
    # Link to job if provided
    if body.job_id:
        from src.services.job_invoice_service import link_job_invoice
        user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
        await link_job_invoice(db, body.job_id, invoice.id, linked_by=user_name)
        await db.commit()
    # Link to case if provided
    if body.case_id:
        invoice.case_id = body.case_id
        await db.commit()
    return _invoice_to_response(invoice)


@router.get("/suggest-jobs")
async def suggest_jobs(
    customer_id: str = Query(...),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Return open/in-progress jobs for a customer, for linking to an estimate.

    Matches jobs by direct customer_id OR via thread's matched_customer_id.
    """
    from sqlalchemy import select, desc, or_
    from src.models.agent_action import AgentAction
    from src.models.agent_thread import AgentThread

    org_id = ctx.organization_id
    active_statuses = ("open", "in_progress", "pending_approval")

    # Direct customer_id match
    q1 = select(AgentAction).where(
        AgentAction.organization_id == org_id,
        AgentAction.customer_id == customer_id,
        AgentAction.status.in_(active_statuses),
    )
    # Thread-based customer match (jobs without direct customer_id)
    q2 = (
        select(AgentAction)
        .join(AgentThread, AgentAction.thread_id == AgentThread.id)
        .where(
            AgentAction.organization_id == org_id,
            AgentAction.customer_id.is_(None),
            AgentThread.matched_customer_id == customer_id,
            AgentAction.status.in_(active_statuses),
        )
    )
    from sqlalchemy import union_all
    combined = union_all(q1, q2).subquery()
    result = await db.execute(
        select(AgentAction)
        .join(combined, AgentAction.id == combined.c.id)
        .order_by(desc(AgentAction.created_at))
        .limit(10)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "description": j.description,
            "action_type": j.action_type,
            "status": j.status,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.get("/monthly", response_model=list)
async def get_monthly_invoices(
    year: int = Query(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if year is None:
        from datetime import date as date_type
        year = date_type.today().year
    svc = InvoiceService(db)
    return await svc.get_monthly(ctx.organization_id, year)


@router.get("/stats", response_model=InvoiceStatsResponse)
async def get_invoice_stats(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    stats = await svc.get_stats(ctx.organization_id)
    return InvoiceStatsResponse(**stats)


@router.get("/{invoice_id}", )
async def get_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and return a PDF for an invoice or estimate."""
    from sqlalchemy import select
    from src.models.organization import Organization
    from src.services.pdf_service import generate_invoice_pdf

    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)

    # Load org for branding
    org_result = await db.execute(select(Organization).where(Organization.id == ctx.organization_id))
    org = org_result.scalar_one()
    org_data = {
        "name": org.name,
        "phone": org.phone,
        "email": org.email,
        "address": org.address,
        "city": org.city,
        "state": org.state,
        "zip_code": org.zip_code,
        "primary_color": org.primary_color,
    }

    customer = invoice.customer
    customer_data = {
        "display_name": customer.display_name if customer else None,
        "company_name": customer.company_name if customer else None,
        "email": customer.email if customer else None,
        "billing_address": customer.billing_address if customer else None,
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

    pdf_bytes = generate_invoice_pdf(org_data, invoice_data, customer_data, line_items_data)

    doc_type = invoice.document_type or "invoice"
    number = invoice.invoice_number or "draft"
    filename = f"{doc_type}_{number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/{invoice_id}", )
async def update_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    data = body.model_dump(exclude_unset=True)
    line_items_data = None
    if "line_items" in data and data["line_items"] is not None:
        line_items_data = data.pop("line_items")
    else:
        data.pop("line_items", None)

    revised_by = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    invoice = await svc.update(
        ctx.organization_id, invoice_id,
        line_items_data=line_items_data,
        revised_by=revised_by,
        **data,
    )
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/send", )
async def send_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    invoice = await svc.send(ctx.organization_id, invoice_id, sent_by=user_name)

    if invoice.document_type == "estimate":
        from src.services.estimate_workflow_service import EstimateWorkflowService
        wf = EstimateWorkflowService(db)
        result = await wf.send_estimate_email(ctx.organization_id, invoice)
        if result.get("sent"):
            await log_job_activity(db, invoice_id, f"Estimate {invoice.invoice_number} sent to {', '.join(result['to'])}")
            await db.commit()
    else:
        await log_job_activity(db, invoice_id, f"Invoice {invoice.invoice_number} marked as sent")
        await db.commit()

    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/void", )
async def void_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    invoice = await svc.void(ctx.organization_id, invoice_id, voided_by=user_name)
    doc = "Estimate" if invoice.document_type == "estimate" else "Invoice"
    await log_job_activity(db, invoice_id, f"{doc} {invoice.invoice_number} voided")
    await db.commit()
    return _invoice_to_response(invoice)


@router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    await svc.delete(ctx.organization_id, invoice_id)
    return {"ok": True}


@router.post("/{invoice_id}/write-off", )
async def write_off_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    invoice = await svc.write_off(ctx.organization_id, invoice_id, written_off_by=user_name)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/approve")
async def approve_estimate(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve an estimate — admin on behalf of client. Creates frozen snapshot."""
    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)

    from src.services.estimate_workflow_service import EstimateWorkflowService
    wf = EstimateWorkflowService(db)
    approver_name = f"{ctx.user.first_name} {ctx.user.last_name}"
    result = await wf.approve_by_admin(ctx.organization_id, invoice, ctx.user.id, approver_name)
    if "error" in result:
        from src.core.exceptions import ValidationError
        raise ValidationError(result["detail"])
    return result


@router.get("/{invoice_id}/approval")
async def get_approval(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get approval record for an estimate."""
    import json
    from sqlalchemy import select
    from src.models.estimate_approval import EstimateApproval

    result = await db.execute(
        select(EstimateApproval).where(
            EstimateApproval.invoice_id == invoice_id,
            EstimateApproval.organization_id == ctx.organization_id,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        return {"approved": False}

    is_approved = approval.approved_by_type and approval.approved_by_type != "pending"

    return {
        "approved": is_approved,
        "has_approval_record": True,
        "id": approval.id,
        "approved_by_type": approval.approved_by_type,
        "approved_by_name": approval.approved_by_name,
        "approval_method": approval.approval_method,
        "notes": approval.notes,
        "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
        "approval_token": approval.approval_token,
        "snapshot": json.loads(approval.snapshot_json),
    }


@router.get("/{invoice_id}/revisions")
async def get_revisions(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get revision history for an invoice."""
    import json
    from sqlalchemy import select
    from src.models.invoice import InvoiceRevision

    # Verify invoice belongs to org
    svc = InvoiceService(db)
    await svc.get(ctx.organization_id, invoice_id)

    result = await db.execute(
        select(InvoiceRevision)
        .where(InvoiceRevision.invoice_id == invoice_id)
        .order_by(InvoiceRevision.revision_number.desc())
    )
    revisions = result.scalars().all()

    return [
        {
            "id": r.id,
            "revision_number": r.revision_number,
            "invoice_number": r.invoice_number_at_revision,
            "revised_by": r.revised_by,
            "created_at": r.created_at.isoformat(),
            "snapshot": json.loads(r.snapshot_json),
        }
        for r in revisions
    ]


@router.post("/{invoice_id}/revise")
async def revise_estimate(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Revise an approved estimate — clears approval so it can be edited and re-approved."""
    from src.core.exceptions import ValidationError

    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)
    if invoice.document_type != "estimate":
        raise ValidationError("Only estimates can be revised")
    if not invoice.approved_at:
        raise ValidationError("Estimate is not approved")

    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    invoice.approved_at = None
    invoice.approved_by = None
    invoice.approval_id = None
    invoice.status = "revised"
    # Append R suffix to estimate number (EST-26004 → EST-26004R, EST-26004R → EST-26004R2, etc.)
    num = invoice.invoice_number or ""
    if num and not num.endswith("R") and not num[-1].isdigit() == False:
        import re
        r_match = re.search(r'R(\d*)$', num)
        if r_match:
            rev = int(r_match.group(1) or "1") + 1
            invoice.invoice_number = re.sub(r'R\d*$', f"R{rev}", num)
        else:
            invoice.invoice_number = f"{num}R"
    await log_job_activity(db, invoice_id, f"Estimate approval revoked for revision by {user_name}")
    await db.commit()
    await db.refresh(invoice)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/convert-to-invoice", )
async def convert_to_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Convert an estimate to an invoice. Assigns a new INV-YYYY-NNNN number."""
    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)
    if invoice.document_type != "estimate":
        from src.core.exceptions import ValidationError
        raise ValidationError("Only estimates can be converted to invoices")
    if not invoice.approved_at:
        from src.core.exceptions import ValidationError
        raise ValidationError("Estimate must be approved before converting to invoice")
    from datetime import datetime, timezone
    old_number = invoice.invoice_number
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    invoice.document_type = "invoice"
    invoice.invoice_number = await svc.next_invoice_number(ctx.organization_id)
    invoice.status = "sent"
    invoice.converted_by = user_name
    invoice.converted_at = datetime.now(timezone.utc)
    await log_job_activity(db, invoice_id, f"Estimate {old_number} converted to invoice {invoice.invoice_number}")
    await db.commit()
    await db.refresh(invoice)
    return _invoice_to_response(invoice)
