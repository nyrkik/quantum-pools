"""Visit endpoints — CRUD + visit experience lifecycle."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.core.database import get_db
from src.core.events import EventType, publish
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.visit import (
    VisitCreate, VisitUpdate, VisitCompleteRequest, VisitResponse,
    ChemicalReadingCreate, ChemicalReadingResponse,
    ServiceCreate, ServiceUpdate, ServiceResponse,
)
from src.services.visit_service import VisitService
from src.services.visit_experience_service import VisitExperienceService, ALLOWED_PHOTO_TYPES, MAX_PHOTO_SIZE
from src.services.chemical_service import ChemicalService
from src.core.exceptions import NotFoundError

router = APIRouter(tags=["visits"])


# --- Pydantic bodies for new endpoints ---

class VisitStartRequest(BaseModel):
    property_id: str
    route_stop_id: Optional[str] = None
    tech_id: Optional[str] = None  # admin override; defaults to logged-in user's tech


class ChecklistUpdateRequest(BaseModel):
    entries: list[dict]  # [{id, completed, notes}]


class VisitReadingCreate(BaseModel):
    water_feature_id: Optional[str] = None
    ph: Optional[float] = None
    free_chlorine: Optional[float] = None
    total_chlorine: Optional[float] = None
    combined_chlorine: Optional[float] = None
    alkalinity: Optional[float] = None
    calcium_hardness: Optional[float] = None
    cyanuric_acid: Optional[float] = None
    tds: Optional[float] = None
    phosphates: Optional[float] = None
    salt: Optional[float] = None
    water_temp: Optional[float] = None
    notes: Optional[str] = None


class VisitCompleteBody(BaseModel):
    notes: Optional[str] = None


class VisitChargeCreate(BaseModel):
    property_id: str
    customer_id: str
    template_id: Optional[str] = None
    description: str
    amount: float
    category: str = "other"
    is_taxable: bool = True
    notes: Optional[str] = None


# --- Helpers ---

def _visit_to_response(visit_data: dict) -> VisitResponse:
    visit = visit_data["visit"]
    resp = VisitResponse.model_validate(visit)
    resp.property_address = visit_data.get("property_address")
    resp.tech_name = visit_data.get("tech_name")
    resp.customer_name = visit_data.get("customer_name")
    return resp


# ======================================================================
# Visit Experience endpoints (new)
# ======================================================================

@router.post("/visits/start")
async def start_visit(
    body: VisitStartRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new in-progress visit. Creates visit + checklist entries."""
    svc = VisitExperienceService(db)
    try:
        # If tech_id override provided (admin), look up that tech's user_id
        tech_user_id = ctx.user.id
        if body.tech_id:
            from sqlalchemy import select
            from src.models.tech import Tech
            result = await db.execute(
                select(Tech).where(
                    Tech.id == body.tech_id,
                    Tech.organization_id == ctx.organization_id,
                )
            )
            tech = result.scalar_one_or_none()
            if not tech:
                raise HTTPException(status_code=404, detail="Tech not found")
            if tech.user_id:
                tech_user_id = tech.user_id

        result = await svc.start_visit(
            ctx.organization_id,
            body.property_id,
            tech_user_id,
            route_stop_id=body.route_stop_id,
        )
        await publish(EventType.VISIT_STARTED, ctx.organization_id, {"visit_id": result.get("visit", {}).get("id"), "property_id": body.property_id})
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/visits/active")
async def get_active_visit(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get in-progress visit for the current tech."""
    svc = VisitExperienceService(db)
    try:
        result = await svc.get_active_visit(ctx.organization_id, ctx.user.id)
    except NotFoundError:
        return None
    return result


@router.get("/visits/history/{property_id}")
async def visit_history(
    property_id: str,
    limit: int = Query(10, ge=1, le=50),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get visit history for a property."""
    svc = VisitExperienceService(db)
    return await svc.get_property_history(ctx.organization_id, property_id, limit=limit)


# ======================================================================
# Existing CRUD endpoints (preserved)
# ======================================================================

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
async def complete_visit_legacy(
    visit_id: str,
    body: VisitCompleteRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy complete endpoint — kept for backward compat."""
    from src.services.events.actor_factory import actor_from_org_ctx
    svc = VisitService(db)
    visit = await svc.complete(ctx.organization_id, visit_id, actor=actor_from_org_ctx(ctx), **body.model_dump(exclude_unset=True))
    return VisitResponse.model_validate(visit)


# ======================================================================
# Visit Experience — context, checklist, readings, photos, complete
# ======================================================================

@router.get("/visits/{visit_id}/context")
async def get_visit_context(
    visit_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Full visit context — single-call fetch for the visit page."""
    svc = VisitExperienceService(db)
    try:
        return await svc.get_context(ctx.organization_id, visit_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/visits/{visit_id}/checklist")
async def update_checklist(
    visit_id: str,
    body: ChecklistUpdateRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update checklist entries."""
    svc = VisitExperienceService(db)
    try:
        return await svc.update_checklist(ctx.organization_id, visit_id, body.entries)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/visits/{visit_id}/readings")
async def create_visit_reading(
    visit_id: str,
    body: VisitReadingCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a chemical reading for this visit."""
    svc = VisitExperienceService(db)
    reading_fields = body.model_dump(exclude={"water_feature_id"}, exclude_unset=True)
    try:
        return await svc.add_reading(
            ctx.organization_id, visit_id, body.water_feature_id, reading_fields,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/visits/{visit_id}/photos")
async def upload_visit_photo(
    visit_id: str,
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    water_feature_id: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a photo for this visit."""
    if not file.content_type or file.content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="File must be JPEG, PNG, or WebP")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    svc = VisitExperienceService(db)
    try:
        return await svc.upload_photo(
            ctx.organization_id, visit_id, file_bytes,
            file.filename or "photo.jpg",
            category=category,
            water_feature_id=water_feature_id,
            caption=caption,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/visits/{visit_id}/photos/{photo_id}", status_code=204)
async def delete_visit_photo(
    visit_id: str,
    photo_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a visit photo."""
    svc = VisitExperienceService(db)
    try:
        await svc.delete_photo(ctx.organization_id, visit_id, photo_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/visits/{visit_id}/charges")
async def create_visit_charge(
    visit_id: str,
    body: VisitChargeCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a charge linked to this visit. Delegates to ChargeService."""
    # Verify visit exists
    svc = VisitExperienceService(db)
    try:
        await svc._get_visit(ctx.organization_id, visit_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    from src.services.charge_service import ChargeService
    charge_svc = ChargeService(db)
    return await charge_svc.create_charge(
        ctx.organization_id,
        ctx.user.id,
        visit_id=visit_id,
        **body.model_dump(),
    )


@router.post("/visits/{visit_id}/finish")
async def finish_visit(
    visit_id: str,
    body: VisitCompleteBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Enhanced complete — calculates duration, marks route stop."""
    from src.services.events.actor_factory import actor_from_org_ctx
    svc = VisitExperienceService(db)
    try:
        result = await svc.complete_visit(ctx.organization_id, visit_id, notes=body.notes, actor=actor_from_org_ctx(ctx))
        await publish(EventType.VISIT_COMPLETED, ctx.organization_id, {"visit_id": visit_id})
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ======================================================================
# Chemical Readings (existing)
# ======================================================================

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
    from src.services.events.actor_factory import actor_from_org_ctx
    svc = ChemicalService(db)
    reading = await svc.create(
        ctx.organization_id,
        actor=actor_from_org_ctx(ctx),
        source="manual",
        **body.model_dump(),
    )
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


# ======================================================================
# Service Catalog (existing)
# ======================================================================

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
