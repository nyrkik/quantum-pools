"""Tech endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.tech import TechCreate, TechUpdate, TechResponse
from src.services.tech_service import TechService

router = APIRouter(prefix="/techs", tags=["techs"])


@router.get("", response_model=list[TechResponse])
async def list_techs(
    is_active: Optional[bool] = Query(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TechService(db)
    techs = await svc.list(ctx.organization_id, is_active=is_active)
    return [TechResponse.model_validate(t) for t in techs]


@router.post("", response_model=TechResponse, status_code=201)
async def create_tech(
    body: TechCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TechService(db)
    tech = await svc.create(ctx.organization_id, **body.model_dump())
    return TechResponse.model_validate(tech)


@router.get("/{tech_id}", response_model=TechResponse)
async def get_tech(
    tech_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TechService(db)
    tech = await svc.get(ctx.organization_id, tech_id)
    return TechResponse.model_validate(tech)


@router.put("/{tech_id}", response_model=TechResponse)
async def update_tech(
    tech_id: str,
    body: TechUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TechService(db)
    tech = await svc.update(ctx.organization_id, tech_id, **body.model_dump(exclude_unset=True))
    return TechResponse.model_validate(tech)


@router.delete("/{tech_id}", status_code=204)
async def delete_tech(
    tech_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TechService(db)
    await svc.delete(ctx.organization_id, tech_id)
