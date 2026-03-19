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


def _invoice_to_response(invoice) -> InvoiceResponse:
    """Convert Invoice model to response, populating customer_name and line_items."""
    resp = InvoiceResponse.model_validate(invoice)
    if invoice.customer:
        resp.customer_name = invoice.customer.display_name
    if hasattr(invoice, "line_items") and invoice.line_items:
        resp.line_items = [InvoiceLineItemResponse.model_validate(li) for li in invoice.line_items]
    return resp


@router.get("", response_model=dict)
async def list_invoices(
    status: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
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
        skip=skip, limit=limit,
    )
    results = [_invoice_to_response(inv) for inv in invoices]
    return {"items": results, "total": total}


@router.post("", response_model=InvoiceResponse, status_code=201)
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


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.get(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.put("/{invoice_id}", response_model=InvoiceResponse)
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


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
async def send_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.send(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/void", response_model=InvoiceResponse)
async def void_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.void(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/write-off", response_model=InvoiceResponse)
async def write_off_invoice(
    invoice_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = InvoiceService(db)
    invoice = await svc.write_off(ctx.organization_id, invoice_id)
    return _invoice_to_response(invoice)
