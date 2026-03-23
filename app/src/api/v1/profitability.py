"""Profitability analysis endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, require_feature, OrgUserContext
from src.models.organization_user import OrgRole
from src.schemas.profitability import (
    OrgCostSettingsUpdate,
    OrgCostSettingsResponse,
    PropertyDifficultyUpdate,
    PropertyDifficultyResponse,
    ProfitabilityOverview,
    PortfolioMedians,
    WhaleCurvePoint,
    PricingSuggestion,
    ProfitabilityAccount,
    JurisdictionResponse,
    BatherLoadRequest,
    BatherLoadResult,
    BulkJurisdictionRequest,
)
from src.services.profitability_service import ProfitabilityService
from src.services.bather_load_service import BatherLoadService
from src.services.property_service import PropertyService
from src.models.water_feature import WaterFeature

router = APIRouter(prefix="/profitability", tags=["profitability"], dependencies=[Depends(require_feature("profitability"))])


# --- Settings ---

@router.get("/settings", response_model=OrgCostSettingsResponse)
async def get_settings(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    settings = await svc.get_or_create_settings(ctx.organization_id)
    return OrgCostSettingsResponse.model_validate(settings)


@router.put("/settings", response_model=OrgCostSettingsResponse)
async def update_settings(
    body: OrgCostSettingsUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    settings = await svc.update_settings(ctx.organization_id, **body.model_dump(exclude_unset=True))
    return OrgCostSettingsResponse.model_validate(settings)


# --- Overview & Analysis ---

@router.get("/overview", response_model=ProfitabilityOverview)
async def get_overview(
    min_margin: Optional[float] = Query(None),
    max_margin: Optional[float] = Query(None),
    min_difficulty: Optional[float] = Query(None),
    max_difficulty: Optional[float] = Query(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    return await svc.get_overview(
        ctx.organization_id,
        min_margin=min_margin,
        max_margin=max_margin,
        min_difficulty=min_difficulty,
        max_difficulty=max_difficulty,
    )


@router.get("/medians", response_model=PortfolioMedians)
async def get_portfolio_medians(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    return await svc.get_portfolio_medians(ctx.organization_id)


@router.get("/account/{customer_id}", response_model=list[ProfitabilityAccount])
async def get_account_detail(
    customer_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    return await svc.get_account_detail(ctx.organization_id, customer_id)


@router.get("/property/{property_id}", response_model=ProfitabilityAccount)
async def get_property_profitability(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get profitability for a single property."""
    from src.models.property import Property
    from sqlalchemy import select
    result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.organization_id == ctx.organization_id,
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    svc = ProfitabilityService(db)
    accounts = await svc.get_account_detail(ctx.organization_id, prop.customer_id)
    for a in accounts:
        if a.property_id == property_id:
            return a
    raise HTTPException(status_code=404, detail="Profitability data not available")


@router.get("/property/{property_id}/rate-allocation")
async def get_rate_allocation(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get per-WF rate allocation for a property."""
    from src.models.property import Property
    from src.models.customer import Customer
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.organization_id == ctx.organization_id,
        ).options(joinedload(Property.customer))
    )
    prop = result.unique().scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    bow_result = await db.execute(
        select(WaterFeature).where(
            WaterFeature.property_id == property_id,
            WaterFeature.organization_id == ctx.organization_id,
            WaterFeature.is_active == True,
        )
    )
    wfs = list(bow_result.scalars().all())
    total_rate = prop.customer.monthly_rate if prop.customer else 0

    return ProfitabilityService.allocate_rate_to_wfs(total_rate, wfs)


@router.get("/whale-curve", response_model=list[WhaleCurvePoint])
async def get_whale_curve(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    return await svc.get_whale_curve(ctx.organization_id)


@router.get("/suggestions", response_model=list[PricingSuggestion])
async def get_suggestions(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProfitabilityService(db)
    return await svc.get_suggestions(ctx.organization_id)


# --- Property Difficulty ---

@router.get("/properties/{property_id}/difficulty", response_model=PropertyDifficultyResponse)
async def get_difficulty(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    prof_svc = ProfitabilityService(db)
    prop_svc = PropertyService(db)
    prop = await prop_svc.get(ctx.organization_id, property_id)
    diff = await prof_svc.get_or_create_difficulty(ctx.organization_id, property_id)
    return prof_svc.get_difficulty_response(prop, diff)


@router.put("/properties/{property_id}/difficulty", response_model=PropertyDifficultyResponse)
async def update_difficulty(
    property_id: str,
    body: PropertyDifficultyUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    prof_svc = ProfitabilityService(db)
    prop_svc = PropertyService(db)
    prop = await prop_svc.get(ctx.organization_id, property_id)
    diff = await prof_svc.update_difficulty(ctx.organization_id, property_id, **body.model_dump(exclude_unset=True))
    return prof_svc.get_difficulty_response(prop, diff)


# --- Jurisdictions & Bather Load ---

@router.get("/jurisdictions", response_model=list[JurisdictionResponse])
async def list_jurisdictions(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = BatherLoadService(db)
    jurisdictions = await svc.list_jurisdictions()
    return [JurisdictionResponse.model_validate(j) for j in jurisdictions]


@router.put("/properties/{property_id}/jurisdiction")
async def assign_jurisdiction(
    property_id: str,
    jurisdiction_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    prop_svc = PropertyService(db)
    await prop_svc.get(ctx.organization_id, property_id)
    bl_svc = BatherLoadService(db)
    await bl_svc.assign_jurisdiction(ctx.organization_id, property_id, jurisdiction_id)
    return {"status": "ok"}


# --- Rate Allocation ---

@router.get("/allocate-rates/{customer_id}")
async def preview_rate_allocation(
    customer_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Preview how a customer's rate would be split across their WFs."""
    svc = ProfitabilityService(db)
    try:
        return await svc.get_rate_allocation_preview(customer_id, ctx.organization_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/apply-rates/{customer_id}")
async def apply_rate_allocation(
    customer_id: str,
    body: dict,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Apply per-WF rates. Body: {"rates": {"wf_id": rate, ...}}."""
    rates = body.get("rates", {})
    if not rates:
        raise HTTPException(status_code=400, detail="No rates provided")
    svc = ProfitabilityService(db)
    try:
        return await svc.apply_rate_allocation(customer_id, ctx.organization_id, rates)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/allocate-rates/bulk")
async def bulk_allocate_rates(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Preview rate allocation for all customers with unallocated WF rates."""
    from sqlalchemy import func, select as sa_select
    from src.models.customer import Customer
    from src.models.property import Property

    # Find customers with multiple WFs where any WF has no rate
    result = await db.execute(
        sa_select(Customer.id)
        .join(Property, Property.customer_id == Customer.id)
        .join(WaterFeature, WaterFeature.property_id == Property.id)
        .where(
            Customer.organization_id == ctx.organization_id,
            Customer.is_active == True,
            WaterFeature.is_active == True,
            WaterFeature.monthly_rate.is_(None),
        )
        .group_by(Customer.id)
        .having(func.count(WaterFeature.id) > 0)
    )
    customer_ids = [r.id for r in result.all()]

    svc = ProfitabilityService(db)
    previews = []
    for cid in customer_ids:
        try:
            preview = await svc.get_rate_allocation_preview(cid, ctx.organization_id)
            if preview.get("allocations"):
                previews.append(preview)
        except Exception:
            continue

    return {"total_customers": len(previews), "previews": previews}


# --- Profit Gaps ---

@router.get("/gaps")
async def get_profit_gaps(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get per-WF profitability sorted by margin (worst first)."""
    svc = ProfitabilityService(db)
    return await svc.get_profit_gaps(ctx.organization_id)


# --- Rate Suggestion ---

@router.get("/suggest-rate")
async def suggest_rate(
    gallons: int = Query(15000),
    water_type: str = Query("pool"),
    service_minutes: int = Query(30),
    difficulty: float = Query(2.5),
    customer_type: str = Query("residential"),
    tier_id: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Suggest a rate for a WF. Residential uses tier-based pricing, commercial uses cost model."""
    svc = ProfitabilityService(db)
    return await svc.suggest_rate(
        org_id=ctx.organization_id,
        gallons=gallons,
        water_type=water_type,
        service_minutes=service_minutes,
        difficulty_score=difficulty,
        customer_type=customer_type,
        tier_id=tier_id,
    )


@router.post("/bulk-jurisdiction")
async def bulk_assign_jurisdiction(
    body: BulkJurisdictionRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = BatherLoadService(db)
    count = await svc.bulk_assign_jurisdiction(
        ctx.organization_id, body.jurisdiction_id,
        city=body.city, zip_code=body.zip_code, state=body.state,
    )
    return {"assigned": count}


@router.get("/properties/{property_id}/bather-load", response_model=BatherLoadResult)
async def get_bather_load(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    prop_svc = PropertyService(db)
    prop = await prop_svc.get(ctx.organization_id, property_id)

    bl_svc = BatherLoadService(db)
    jurisdiction = await bl_svc.get_property_jurisdiction(ctx.organization_id, property_id)
    if not jurisdiction:
        jurisdiction = await bl_svc.get_default_jurisdiction()

    prof_svc = ProfitabilityService(db)
    diff = await prof_svc.get_or_create_difficulty(ctx.organization_id, property_id)

    return bl_svc.calculate(
        jurisdiction,
        pool_sqft=prop.pool_sqft,
        pool_gallons=prop.pool_gallons,
        shallow_sqft=diff.shallow_sqft,
        deep_sqft=diff.deep_sqft,
        has_deep_end=diff.has_deep_end,
        spa_sqft=diff.spa_sqft,
        diving_board_count=diff.diving_board_count,
        pump_flow_gpm=diff.pump_flow_gpm,
        is_indoor=diff.is_indoor,
    )


@router.post("/bather-load/calculate", response_model=BatherLoadResult)
async def calculate_bather_load(
    body: BatherLoadRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Standalone bather load calculator — no property needed."""
    bl_svc = BatherLoadService(db)
    if body.jurisdiction_id:
        jurisdiction = await bl_svc.get_jurisdiction(body.jurisdiction_id)
    else:
        jurisdiction = await bl_svc.get_default_jurisdiction()

    return bl_svc.calculate(
        jurisdiction,
        pool_sqft=body.pool_sqft,
        pool_gallons=body.pool_gallons,
        shallow_sqft=body.shallow_sqft,
        deep_sqft=body.deep_sqft,
        has_deep_end=body.has_deep_end,
        spa_sqft=body.spa_sqft,
        diving_board_count=body.diving_board_count,
        pump_flow_gpm=body.pump_flow_gpm,
        is_indoor=body.is_indoor,
    )
