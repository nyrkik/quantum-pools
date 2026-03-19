"""Property endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db, get_db_context
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.property import PropertyCreate, PropertyUpdate, PropertyResponse
from src.services.property_service import PropertyService
from src.services.geocoding_service import GeocodingService
from src.services.body_of_water_service import BodyOfWaterService

router = APIRouter(prefix="/properties", tags=["properties"])


async def _geocode_property(property_id: str, address: str):
    """Background task to geocode a property."""
    async with get_db_context() as db:
        geo_svc = GeocodingService(db)
        result = await geo_svc.geocode(address)
        if result:
            prop_svc = PropertyService(db)
            await prop_svc.update_geocode(property_id, result[0], result[1], result[2])


async def _emd_auto_match(organization_id: str):
    """Background task to auto-match EMD facilities after property changes."""
    try:
        async with get_db_context() as db:
            from src.services.emd.service import EMDService
            svc = EMDService(db)
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
    svc = PropertyService(db)
    bow_svc = BodyOfWaterService(db)
    properties, total = await svc.list(
        ctx.organization_id, customer_id=customer_id, is_active=is_active, skip=skip, limit=limit
    )
    results = []
    for p in properties:
        resp = PropertyResponse.model_validate(p)
        resp.bodies_of_water = [
            {"id": b.id, "name": b.name, "water_type": b.water_type,
             "pool_type": b.pool_type, "pool_gallons": b.pool_gallons, "pool_sqft": b.pool_sqft,
             "estimated_service_minutes": b.estimated_service_minutes, "monthly_rate": b.monthly_rate}
            for b in await bow_svc.list_for_property(ctx.organization_id, p.id)
        ]
        results.append(resp)
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
    background_tasks.add_task(_emd_auto_match, ctx.organization_id)
    return PropertyResponse.model_validate(prop)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyService(db)
    bow_svc = BodyOfWaterService(db)
    prop = await svc.get(ctx.organization_id, property_id)
    resp = PropertyResponse.model_validate(prop)
    resp.bodies_of_water = [
        {"id": b.id, "name": b.name, "water_type": b.water_type,
         "pool_type": b.pool_type, "pool_gallons": b.pool_gallons, "pool_sqft": b.pool_sqft,
         "estimated_service_minutes": b.estimated_service_minutes, "monthly_rate": b.monthly_rate}
        for b in await bow_svc.list_for_property(ctx.organization_id, prop.id)
    ]
    return resp


@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: str,
    body: PropertyUpdate,
    background_tasks: BackgroundTasks,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyService(db)
    prop, address_changed = await svc.update(
        ctx.organization_id, property_id, **body.model_dump(exclude_unset=True)
    )
    if address_changed:
        background_tasks.add_task(_geocode_property, prop.id, prop.full_address)
        background_tasks.add_task(_emd_auto_match, ctx.organization_id)
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
