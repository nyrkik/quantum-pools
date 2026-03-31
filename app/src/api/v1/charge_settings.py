"""Charge & billing settings — thresholds, payment terms, estimate terms."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from src.core.database import get_db
from src.api.deps import require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.models.org_cost_settings import OrgCostSettings
from src.services.charge_service import ChargeService

router = APIRouter(prefix="/charge-settings", tags=["charge-settings"])


class ThresholdUpdate(BaseModel):
    auto_approve_threshold: Optional[float] = None
    separate_invoice_threshold: Optional[float] = None
    require_photo_threshold: Optional[float] = None


class BillingTermsUpdate(BaseModel):
    payment_terms_days: Optional[int] = None
    estimate_validity_days: Optional[int] = None
    late_fee_pct: Optional[float] = None
    warranty_days: Optional[int] = None
    billable_labor_rate: Optional[float] = None
    estimate_terms: Optional[str] = None


@router.get("")
async def get_thresholds(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    return await svc.get_thresholds(ctx.organization_id)


@router.put("")
async def update_thresholds(
    body: ThresholdUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    try:
        return await svc.update_thresholds(
            ctx.organization_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/billing-terms")
async def get_billing_terms(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgCostSettings).where(OrgCostSettings.organization_id == ctx.organization_id)
    )
    settings = result.scalar_one_or_none()
    return {
        "payment_terms_days": settings.payment_terms_days if settings else 30,
        "estimate_validity_days": settings.estimate_validity_days if settings else 30,
        "late_fee_pct": settings.late_fee_pct if settings else 1.5,
        "warranty_days": settings.warranty_days if settings else 30,
        "billable_labor_rate": settings.billable_labor_rate if settings and hasattr(settings, "billable_labor_rate") else 125.0,
        "estimate_terms": settings.estimate_terms if settings else None,
    }


@router.put("/billing-terms")
async def update_billing_terms(
    body: BillingTermsUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgCostSettings).where(OrgCostSettings.organization_id == ctx.organization_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        import uuid
        settings = OrgCostSettings(id=str(uuid.uuid4()), organization_id=ctx.organization_id)
        db.add(settings)

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)
    return {
        "payment_terms_days": settings.payment_terms_days,
        "estimate_validity_days": settings.estimate_validity_days,
        "late_fee_pct": settings.late_fee_pct,
        "warranty_days": settings.warranty_days,
        "billable_labor_rate": settings.billable_labor_rate if hasattr(settings, "billable_labor_rate") else 125.0,
        "estimate_terms": settings.estimate_terms,
    }
