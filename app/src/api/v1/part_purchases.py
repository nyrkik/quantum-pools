"""Part purchases — log and query part cost records."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.part_purchase_service import PartPurchaseService

router = APIRouter(prefix="/part-purchases", tags=["part-purchases"])


class PurchaseCreate(BaseModel):
    description: str
    vendor_name: str
    unit_cost: float
    quantity: int = 1
    sku: Optional[str] = None
    catalog_part_id: Optional[str] = None
    markup_pct: Optional[float] = None
    visit_charge_id: Optional[str] = None
    job_id: Optional[str] = None
    property_id: Optional[str] = None
    water_feature_id: Optional[str] = None
    purchased_at: Optional[str] = None
    receipt_url: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_purchase(
    body: PurchaseCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PartPurchaseService(db)
    return await svc.create_purchase(
        ctx.organization_id, ctx.user.id,
        **body.model_dump(exclude_unset=True),
    )


@router.get("")
async def list_purchases(
    property_id: Optional[str] = None,
    job_id: Optional[str] = None,
    vendor_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PartPurchaseService(db)
    return await svc.list_purchases(
        ctx.organization_id,
        property_id=property_id,
        job_id=job_id,
        vendor_name=vendor_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/job/{job_id}")
async def get_job_parts(
    job_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PartPurchaseService(db)
    return await svc.get_job_parts(ctx.organization_id, job_id)


@router.get("/summary")
async def get_purchase_summary(
    months: int = Query(3, ge=1, le=24),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PartPurchaseService(db)
    return await svc.get_purchase_summary(ctx.organization_id, months)


@router.get("/markup")
async def get_markup(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PartPurchaseService(db)
    markup = await svc.get_markup(ctx.organization_id)
    return {"default_parts_markup_pct": markup}


@router.delete("/{purchase_id}", status_code=204)
async def delete_purchase(
    purchase_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = PartPurchaseService(db)
    deleted = await svc.delete_purchase(ctx.organization_id, purchase_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Purchase not found")
