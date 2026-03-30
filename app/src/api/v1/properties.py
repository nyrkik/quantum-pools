"""Property endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db, get_db_context
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.property import PropertyCreate, PropertyUpdate, PropertyResponse
from src.services.property_service import PropertyService
from src.services.geocoding_service import GeocodingService
from src.services.water_feature_service import WaterFeatureService

router = APIRouter(prefix="/properties", tags=["properties"])


async def _geocode_property(property_id: str, address: str):
    """Background task to geocode a property."""
    async with get_db_context() as db:
        geo_svc = GeocodingService(db)
        result = await geo_svc.geocode(address)
        if result:
            prop_svc = PropertyService(db)
            await prop_svc.update_geocode(property_id, result[0], result[1], result[2])


async def _inspection_auto_match(organization_id: str):
    """Background task to auto-match EMD facilities after property changes."""
    try:
        async with get_db_context() as db:
            from src.services.inspection.service import InspectionService
            svc = InspectionService(db)
            await svc.auto_match_facilities(organization_id)
    except Exception:
        pass  # Non-critical


@router.get("", response_model=dict)
async def list_properties(
    customer_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.presenters.property_presenter import PropertyPresenter

    svc = PropertyService(db)
    wf_svc = WaterFeatureService(db)
    properties, total = await svc.list(
        ctx.organization_id, customer_id=customer_id, is_active=is_active, skip=skip, limit=limit
    )
    # Build WF map for batch presentation
    wf_map = {}
    for p in properties:
        wf_map[p.id] = await wf_svc.list_for_property(ctx.organization_id, p.id)

    presenter = PropertyPresenter(db)
    results = await presenter.many(properties, wf_map=wf_map)
    return {"items": results, "total": total}


@router.post("", response_model=PropertyResponse, status_code=201)
async def create_property(
    body: PropertyCreate,
    background_tasks: BackgroundTasks,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyService(db)
    prop = await svc.create(ctx.organization_id, **body.model_dump())
    background_tasks.add_task(_geocode_property, prop.id, prop.full_address)
    background_tasks.add_task(_inspection_auto_match, ctx.organization_id)
    return PropertyResponse.model_validate(prop)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.presenters.property_presenter import PropertyPresenter

    svc = PropertyService(db)
    wf_svc = WaterFeatureService(db)
    prop = await svc.get(ctx.organization_id, property_id)
    wfs = await wf_svc.list_for_property(ctx.organization_id, prop.id)
    presenter = PropertyPresenter(db)
    return await presenter.one(prop, water_features=wfs)


@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: str,
    body: PropertyUpdate,
    background_tasks: BackgroundTasks,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyService(db)
    update_data = body.model_dump(exclude_unset=True)
    rate_changed = "monthly_rate" in update_data
    prop, address_changed = await svc.update(
        ctx.organization_id, property_id, **update_data
    )
    if address_changed:
        background_tasks.add_task(_geocode_property, prop.id, prop.full_address)
        background_tasks.add_task(_inspection_auto_match, ctx.organization_id)
    if rate_changed:
        from src.models.water_feature import WaterFeature
        from src.services.profitability_service import ProfitabilityService
        from src.services.rate_sync import sync_rates_for_property
        from sqlalchemy import select

        # Split property rate down to its WFs
        bows_result = await db.execute(
            select(WaterFeature).where(
                WaterFeature.property_id == property_id,
                WaterFeature.is_active == True,
            )
        )
        wfs = bows_result.scalars().all()
        if wfs:
            new_rate = update_data["monthly_rate"] or 0
            allocation = ProfitabilityService.allocate_rate_to_wfs(new_rate, wfs)
            for wf in wfs:
                alloc = allocation.get(wf.id, {})
                wf.monthly_rate = alloc.get("allocated_rate", new_rate / len(wfs))
                wf.rate_allocation_method = alloc.get("allocation_method", "equal")
            await db.flush()

        # Sync property + customer totals
        await sync_rates_for_property(db, property_id)
    return PropertyResponse.model_validate(prop)


@router.delete("/{property_id}", status_code=204)
async def delete_property(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyService(db)
    await svc.delete(ctx.organization_id, property_id)


@router.post("/{property_id}/geocode", response_model=dict)
async def geocode_property(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    prop_svc = PropertyService(db)
    prop = await prop_svc.get(ctx.organization_id, property_id)
    geo_svc = GeocodingService(db)
    result = await geo_svc.geocode(prop.full_address)
    if result:
        await prop_svc.update_geocode(prop.id, result[0], result[1], result[2])
        return {"lat": result[0], "lng": result[1], "provider": result[2]}
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not geocode address")
