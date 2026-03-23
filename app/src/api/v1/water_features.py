"""Body of Water endpoints — CRUD for individual bodies of water within properties."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.water_feature import WaterFeatureCreate, WaterFeatureUpdate, WaterFeatureResponse
from src.services.water_feature_service import WaterFeatureService

router = APIRouter(prefix="/water-features", tags=["water-features"])


@router.get("/property/{property_id}", response_model=list[WaterFeatureResponse])
async def list_water_features(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WaterFeatureService(db)
    wfs = await svc.list_for_property(ctx.organization_id, property_id)
    return [WaterFeatureResponse.model_validate(b) for b in wfs]


@router.post("/property/{property_id}", response_model=WaterFeatureResponse, status_code=201)
async def create_water_feature(
    property_id: str,
    body: WaterFeatureCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WaterFeatureService(db)
    wf = await svc.create(ctx.organization_id, property_id, **body.model_dump())
    return WaterFeatureResponse.model_validate(wf)


@router.get("/{wf_id}", response_model=WaterFeatureResponse)
async def get_water_feature(
    wf_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WaterFeatureService(db)
    wf = await svc.get(ctx.organization_id, wf_id)
    return WaterFeatureResponse.model_validate(wf)


@router.put("/{wf_id}", response_model=WaterFeatureResponse)
async def update_water_feature(
    wf_id: str,
    body: WaterFeatureUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WaterFeatureService(db)
    wf = await svc.update(ctx.organization_id, wf_id, **body.model_dump(exclude_unset=True))
    return WaterFeatureResponse.model_validate(wf)


@router.delete("/{wf_id}", status_code=204)
async def delete_water_feature(
    wf_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WaterFeatureService(db)
    await svc.delete(ctx.organization_id, wf_id)
