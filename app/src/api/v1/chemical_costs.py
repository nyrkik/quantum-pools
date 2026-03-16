"""Chemical cost engine API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.schemas.chemical_costs import (
    RegionalDefaultResponse,
    OrgChemicalPricesUpdate,
    OrgChemicalPricesResponse,
    ChemicalCostProfileResponse,
    ChemicalCostProfileUpdate,
)
from src.services.chemical_cost_service import ChemicalCostService

router = APIRouter(prefix="/chemical-costs", tags=["chemical-costs"])


# --- Regional Defaults ---

@router.get("/defaults/{region_key}", response_model=list[RegionalDefaultResponse])
async def get_regional_defaults(
    region_key: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all regional chemical defaults for a region."""
    svc = ChemicalCostService(db)
    defaults = await svc.get_all_regional_defaults(region_key)
    return [RegionalDefaultResponse.model_validate(d) for d in defaults]


# --- Org Chemical Prices ---

@router.get("/org-prices", response_model=OrgChemicalPricesResponse)
async def get_org_prices(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get org chemical price overrides."""
    svc = ChemicalCostService(db)
    prices = await svc.get_or_create_org_prices(ctx.organization_id)
    return OrgChemicalPricesResponse.model_validate(prices)


@router.put("/org-prices", response_model=OrgChemicalPricesResponse)
async def update_org_prices(
    body: OrgChemicalPricesUpdate,
    recompute: bool = Query(False, description="Recompute all BOW costs after price update"),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update org chemical price overrides. Optionally recompute all BOW costs."""
    svc = ChemicalCostService(db)
    prices = await svc.update_org_prices(ctx.organization_id, **body.model_dump(exclude_unset=True))
    if recompute:
        await svc.recompute_all(ctx.organization_id)
    return OrgChemicalPricesResponse.model_validate(prices)


# --- BOW Chemical Cost Profiles ---

@router.get("/bows/{bow_id}", response_model=ChemicalCostProfileResponse)
async def get_bow_chemical_cost(
    bow_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or compute chemical cost profile for a body of water."""
    svc = ChemicalCostService(db)
    profile = await svc.get_or_compute(ctx.organization_id, bow_id)
    return ChemicalCostProfileResponse.model_validate(profile)


@router.put("/bows/{bow_id}", response_model=ChemicalCostProfileResponse)
async def update_bow_chemical_cost(
    bow_id: str,
    body: ChemicalCostProfileUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Override BOW-level chemical costs or usage rates."""
    svc = ChemicalCostService(db)
    profile = await svc.update_bow_overrides(ctx.organization_id, bow_id, **body.model_dump(exclude_unset=True))
    return ChemicalCostProfileResponse.model_validate(profile)


# --- Recompute ---

@router.post("/recompute")
async def recompute_all(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Recompute all BOW chemical costs for the org."""
    svc = ChemicalCostService(db)
    count = await svc.recompute_all(ctx.organization_id)
    return {"recomputed": count}
