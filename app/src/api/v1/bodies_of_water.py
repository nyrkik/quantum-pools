"""Body of Water endpoints — CRUD for individual bodies of water within properties."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.body_of_water import BodyOfWaterCreate, BodyOfWaterUpdate, BodyOfWaterResponse
from src.services.body_of_water_service import BodyOfWaterService

router = APIRouter(prefix="/bodies-of-water", tags=["bodies-of-water"])


@router.get("/property/{property_id}", response_model=list[BodyOfWaterResponse])
async def list_bodies_of_water(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = BodyOfWaterService(db)
    bows = await svc.list_for_property(ctx.organization_id, property_id)
    return [BodyOfWaterResponse.model_validate(b) for b in bows]


@router.post("/property/{property_id}", response_model=BodyOfWaterResponse, status_code=201)
async def create_body_of_water(
    property_id: str,
    body: BodyOfWaterCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = BodyOfWaterService(db)
    bow = await svc.create(ctx.organization_id, property_id, **body.model_dump())
    return BodyOfWaterResponse.model_validate(bow)


@router.get("/{bow_id}", response_model=BodyOfWaterResponse)
async def get_body_of_water(
    bow_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = BodyOfWaterService(db)
    bow = await svc.get(ctx.organization_id, bow_id)
    return BodyOfWaterResponse.model_validate(bow)


@router.put("/{bow_id}", response_model=BodyOfWaterResponse)
async def update_body_of_water(
    bow_id: str,
    body: BodyOfWaterUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = BodyOfWaterService(db)
    bow = await svc.update(ctx.organization_id, bow_id, **body.model_dump(exclude_unset=True))
    return BodyOfWaterResponse.model_validate(bow)


@router.delete("/{bow_id}", status_code=204)
async def delete_body_of_water(
    bow_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = BodyOfWaterService(db)
    await svc.delete(ctx.organization_id, bow_id)
