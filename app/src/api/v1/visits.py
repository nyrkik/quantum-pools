"""Visit endpoints."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.visit import (
    VisitCreate, VisitUpdate, VisitCompleteRequest, VisitResponse,
    ChemicalReadingCreate, ChemicalReadingResponse,
    ServiceCreate, ServiceUpdate, ServiceResponse,
)
from src.services.visit_service import VisitService
from src.services.chemical_service import ChemicalService

router = APIRouter(tags=["visits"])


def _visit_to_response(visit_data: dict) -> VisitResponse:
    visit = visit_data["visit"]
    resp = VisitResponse.model_validate(visit)
    resp.property_address = visit_data.get("property_address")
    resp.tech_name = visit_data.get("tech_name")
    resp.customer_name = visit_data.get("customer_name")
    return resp


# --- Visits ---

@router.get("/visits", response_model=dict)
async def list_visits(
    scheduled_date: Optional[date] = Query(None),
    tech_id: Optional[str] = Query(None),
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VisitService(db)
    visits, total = await svc.list(
        ctx.organization_id, scheduled_date=scheduled_date, tech_id=tech_id,
        property_id=property_id, status=status, skip=skip, limit=limit,
    )
    return {"items": [_visit_to_response(v) for v in visits], "total": total}


@router.get("/visits/today", response_model=list[VisitResponse])
async def today_visits(
    tech_id: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VisitService(db)
    visits = await svc.today(ctx.organization_id, tech_id=tech_id)
    return [_visit_to_response(v) for v in visits]


@router.post("/visits", response_model=VisitResponse, status_code=201)
async def create_visit(
    body: VisitCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VisitService(db)
    visit = await svc.create(ctx.organization_id, **body.model_dump())
    return VisitResponse.model_validate(visit)


@router.get("/visits/{visit_id}", response_model=VisitResponse)
async def get_visit(
    visit_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VisitService(db)
    visit = await svc.get(ctx.organization_id, visit_id)
    return VisitResponse.model_validate(visit)


@router.put("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    visit_id: str,
    body: VisitUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VisitService(db)
    visit = await svc.update(ctx.organization_id, visit_id, **body.model_dump(exclude_unset=True))
    return VisitResponse.model_validate(visit)


@router.post("/visits/{visit_id}/complete", response_model=VisitResponse)
async def complete_visit(
    visit_id: str,
    body: VisitCompleteRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VisitService(db)
    visit = await svc.complete(ctx.organization_id, visit_id, **body.model_dump(exclude_unset=True))
    return VisitResponse.model_validate(visit)


# --- Chemical Readings ---

@router.get("/readings/property/{property_id}", response_model=list[ChemicalReadingResponse])
async def list_readings(
    property_id: str,
    limit: int = Query(50, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChemicalService(db)
    readings = await svc.list_for_property(ctx.organization_id, property_id, limit=limit)
    return [ChemicalReadingResponse.model_validate(r) for r in readings]


@router.post("/readings", response_model=ChemicalReadingResponse, status_code=201)
async def create_reading(
    body: ChemicalReadingCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChemicalService(db)
    reading = await svc.create(ctx.organization_id, **body.model_dump())
    return ChemicalReadingResponse.model_validate(reading)


@router.get("/readings/{reading_id}/recommendations", response_model=dict)
async def get_recommendations(
    reading_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChemicalService(db)
    reading = await svc.get(ctx.organization_id, reading_id)
    return reading.recommendations or {"issues": [], "actions": []}


# --- Service Catalog ---

@router.get("/services", response_model=list[ServiceResponse])
async def list_services(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from src.models.service import Service
    result = await db.execute(
        select(Service).where(Service.organization_id == ctx.organization_id, Service.is_active == True)
        .order_by(Service.name)
    )
    return [ServiceResponse.model_validate(s) for s in result.scalars().all()]


@router.post("/services", response_model=ServiceResponse, status_code=201)
async def create_service(
    body: ServiceCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    from src.models.service import Service
    svc = Service(id=str(uuid.uuid4()), organization_id=ctx.organization_id, **body.model_dump())
    db.add(svc)
    await db.flush()
    await db.refresh(svc)
    return ServiceResponse.model_validate(svc)
