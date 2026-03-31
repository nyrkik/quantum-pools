"""Payment endpoints — all org-scoped."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_feature, OrgUserContext
from src.schemas.payment import PaymentCreate, PaymentResponse
from src.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(require_feature("invoicing"))])


def _payment_to_response(payment) -> PaymentResponse:
    """Convert Payment model to response, populating customer_name and invoice_number."""
    resp = PaymentResponse.model_validate(payment)
    if payment.customer:
        resp.customer_name = payment.customer.display_name
    if payment.invoice:
        resp.invoice_number = payment.invoice.invoice_number
    return resp


@router.get("", response_model=dict)
async def list_payments(
    customer_id: Optional[str] = Query(None),
    invoice_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PaymentService(db)
    payments, total = await svc.list(
        ctx.organization_id, customer_id=customer_id, invoice_id=invoice_id,
        skip=skip, limit=limit,
    )
    results = [_payment_to_response(p) for p in payments]
    return {"items": results, "total": total}


@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(
    body: PaymentCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PaymentService(db)
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    payment = await svc.create(ctx.organization_id, **body.model_dump(), recorded_by=user_name)
    if body.invoice_id:
        from src.services.invoice_service import log_job_activity
        method = body.payment_method.replace("_", " ").title() if body.payment_method else "Payment"
        await log_job_activity(db, body.invoice_id, f"Payment recorded: ${body.amount:,.2f} ({method})")
        await db.commit()
    return PaymentResponse.model_validate(payment)
