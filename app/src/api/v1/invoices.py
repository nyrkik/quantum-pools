"""Invoice endpoints — all org-scoped."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import NotFoundError, ValidationError
from src.api.deps import get_current_org_user, require_feature, OrgUserContext
from src.schemas.invoice import InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceLineItemResponse, InvoiceStatsResponse
from src.services.invoice_service import InvoiceService

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
    )
    return _invoice_to_response(invoice)


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

    invoice = await svc.update(
        ctx.organization_id, invoice_id,
        line_items_data=line_items_data,
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
    invoice = await svc.send(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/void", )
async def void_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.void(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/write-off", )
async def write_off_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.write_off(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/approve")
async def approve_estimate(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve an estimate — admin on behalf of client. Creates frozen snapshot."""
    import json
    from datetime import datetime, timezone
    from pydantic import BaseModel
    from src.models.estimate_approval import EstimateApproval

    class ApproveBody(BaseModel):
        notes: Optional[str] = None
        client_name: Optional[str] = None

    # Parse body manually since we defined inline
    from fastapi import Request
    body_raw = {}
    try:
        import starlette
    except:
        pass

    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)

    if invoice.document_type != "estimate":
        from src.core.exceptions import ValidationError
        raise ValidationError("Only estimates can be approved")

    if invoice.approved_at:
        from src.core.exceptions import ValidationError
        raise ValidationError("Estimate is already approved")

    # Build frozen snapshot
    snapshot = {
        "estimate_number": invoice.invoice_number,
        "customer_name": invoice.customer.display_name if invoice.customer else "",
        "subject": invoice.subject,
        "line_items": [
            {
                "description": li.description,
                "quantity": li.quantity,
                "unit_price": li.unit_price,
                "amount": li.amount,
            }
            for li in (invoice.line_items or [])
        ],
        "subtotal": invoice.subtotal,
        "discount": invoice.discount,
        "tax_rate": invoice.tax_rate,
        "tax_amount": invoice.tax_amount,
        "total": invoice.total,
        "notes": invoice.notes,
        "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
    }

    now = datetime.now(timezone.utc)
    approver_name = f"{ctx.user.first_name} {ctx.user.last_name}"

    approval = EstimateApproval(
        organization_id=ctx.organization_id,
        invoice_id=invoice_id,
        approved_by_type="admin_on_behalf",
        approved_by_name=approver_name,
        approved_by_user_id=ctx.user.id,
        approval_method="admin_dashboard",
        snapshot_json=json.dumps(snapshot),
        approved_at=now,
    )
    db.add(approval)
    await db.flush()

    invoice.approved_at = now
    invoice.approved_by = approver_name
    invoice.approval_id = approval.id

    # Create or update linked job
    from src.models.agent_action import AgentAction
    action_result = await db.execute(
        select(AgentAction).where(AgentAction.invoice_id == invoice_id)
    )
    action = action_result.scalar_one_or_none()
    if action:
        action.status = "approved"
    else:
        action = AgentAction(
            organization_id=ctx.organization_id,
            invoice_id=invoice_id,
            customer_id=invoice.customer_id,
            action_type="repair",
            description=f"Approved: {invoice.subject or 'Service Estimate'}",
            status="approved",
            job_path="customer",
            created_by=approver_name,
        )
        db.add(action)

    await db.commit()

    return {
        "approved": True,
        "approval_id": approval.id,
        "approved_by": approver_name,
        "approved_at": now.isoformat(),
        "approval_token": approval.approval_token,
    }


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

    return {
        "approved": True,
        "id": approval.id,
        "approved_by_type": approval.approved_by_type,
        "approved_by_name": approval.approved_by_name,
        "approval_method": approval.approval_method,
        "notes": approval.notes,
        "approved_at": approval.approved_at.isoformat(),
        "snapshot": json.loads(approval.snapshot_json),
    }


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
    invoice.document_type = "invoice"
    invoice.invoice_number = await svc.next_invoice_number(ctx.organization_id)
    await db.commit()
    await db.refresh(invoice)
    return _invoice_to_response(invoice)
