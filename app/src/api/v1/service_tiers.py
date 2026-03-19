"""Service tier endpoints — per-org residential service packages."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.models.service_tier import ServiceTier
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/service-tiers", tags=["service-tiers"])


class ServiceTierResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int
    base_rate: float
    estimated_minutes: int
    includes_chems: bool
    includes_skim: bool
    includes_baskets: bool
    includes_vacuum: bool
    includes_brush: bool
    includes_equipment_check: bool
    is_default: bool
    is_active: bool

    model_config = {"from_attributes": True}


class ServiceTierCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int = 0
    base_rate: float = 0.0
    estimated_minutes: int = 30
    includes_chems: bool = True
    includes_skim: bool = False
    includes_baskets: bool = False
    includes_vacuum: bool = False
    includes_brush: bool = False
    includes_equipment_check: bool = False
    is_default: bool = False


class ServiceTierUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    base_rate: Optional[float] = None
    estimated_minutes: Optional[int] = None
    includes_chems: Optional[bool] = None
    includes_skim: Optional[bool] = None
    includes_baskets: Optional[bool] = None
    includes_vacuum: Optional[bool] = None
    includes_brush: Optional[bool] = None
    includes_equipment_check: Optional[bool] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


@router.get("", response_model=list[ServiceTierResponse])
async def list_tiers(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ServiceTier)
        .where(ServiceTier.organization_id == ctx.organization_id, ServiceTier.is_active == True)
        .order_by(ServiceTier.sort_order)
    )
    return [ServiceTierResponse.model_validate(t) for t in result.scalars().all()]


@router.post("", response_model=ServiceTierResponse, status_code=status.HTTP_201_CREATED)
async def create_tier(
    body: ServiceTierCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    tier = ServiceTier(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        **body.model_dump(),
    )
    if body.is_default:
        # Clear other defaults
        result = await db.execute(
            select(ServiceTier).where(
                ServiceTier.organization_id == ctx.organization_id,
                ServiceTier.is_default == True,
            )
        )
        for t in result.scalars().all():
            t.is_default = False

    db.add(tier)
    await db.flush()
    return ServiceTierResponse.model_validate(tier)


@router.put("/{tier_id}", response_model=ServiceTierResponse)
async def update_tier(
    tier_id: str,
    body: ServiceTierUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ServiceTier).where(
            ServiceTier.id == tier_id,
            ServiceTier.organization_id == ctx.organization_id,
        )
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    updates = body.model_dump(exclude_unset=True)
    if updates.get("is_default"):
        # Clear other defaults
        others = await db.execute(
            select(ServiceTier).where(
                ServiceTier.organization_id == ctx.organization_id,
                ServiceTier.is_default == True,
                ServiceTier.id != tier_id,
            )
        )
        for t in others.scalars().all():
            t.is_default = False

    for k, v in updates.items():
        setattr(tier, k, v)
    await db.flush()
    return ServiceTierResponse.model_validate(tier)


@router.delete("/{tier_id}")
async def delete_tier(
    tier_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ServiceTier).where(
            ServiceTier.id == tier_id,
            ServiceTier.organization_id == ctx.organization_id,
        )
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    tier.is_active = False
    await db.flush()
    return {"deleted": True}
