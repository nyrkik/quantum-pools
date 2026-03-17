"""EMD inspection intelligence endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.schemas.emd import (
    EMDFacilityListResponse,
    EMDFacilityDetailResponse,
    EMDInspectionResponse,
    EMDInspectionDetailResponse,
    EMDViolationResponse,
    EMDEquipmentResponse,
    EMDLeadResponse,
    ScrapeRequest,
    MatchFacilityRequest,
)
from src.services.emd.service import EMDService

router = APIRouter(prefix="/emd", tags=["emd"])


@router.get("/facilities", response_model=list[EMDFacilityListResponse])
async def list_facilities(
    search: Optional[str] = Query(None),
    matched_only: bool = Query(False),
    limit: int = Query(2000, le=5000),
    offset: int = Query(0),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all EMD facilities with summary stats."""
    svc = EMDService(db)
    facilities, total = await svc.list_facilities(
        search=search, matched_only=matched_only, limit=limit, offset=offset
    )
    return [EMDFacilityListResponse(**f) for f in facilities]


@router.get("/facilities/{facility_id}")
async def get_facility_detail(
    facility_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get facility detail with full inspection history."""
    svc = EMDService(db)
    detail = await svc.get_facility_detail(facility_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found")

    facility = detail["facility"]
    return EMDFacilityDetailResponse(
        id=facility.id,
        organization_id=facility.organization_id,
        name=facility.name,
        street_address=facility.street_address,
        city=facility.city,
        state=facility.state,
        zip_code=facility.zip_code,
        phone=facility.phone,
        facility_id=facility.facility_id,
        permit_holder=facility.permit_holder,
        facility_type=facility.facility_type,
        matched_property_id=facility.matched_property_id,
        matched_at=facility.matched_at,
        created_at=facility.created_at,
        updated_at=facility.updated_at,
        inspections=[EMDInspectionDetailResponse.model_validate(i) for i in detail["inspections"]],
        total_inspections=detail["total_inspections"],
        total_violations=detail["total_violations"],
        last_inspection_date=detail["last_inspection_date"],
        matched_property_address=detail["matched_property_address"],
        matched_customer_name=detail["matched_customer_name"],
    )


@router.get("/facilities/{facility_id}/inspections", response_model=list[EMDInspectionResponse])
async def get_facility_inspections(
    facility_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all inspections for a facility."""
    svc = EMDService(db)
    inspections = await svc.get_facility_inspections(facility_id)
    return [EMDInspectionResponse.model_validate(i) for i in inspections]


@router.get("/facilities/{facility_id}/equipment", response_model=Optional[EMDEquipmentResponse])
async def get_facility_equipment(
    facility_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get latest equipment data for a facility."""
    svc = EMDService(db)
    equipment = await svc.get_facility_equipment(facility_id)
    if not equipment:
        return None
    return EMDEquipmentResponse.model_validate(equipment)


@router.post("/scrape")
async def trigger_scrape(
    body: ScrapeRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a scrape for a date range (admin only)."""
    svc = EMDService(db)
    try:
        result = await svc.scrape_date_range(
            start_date=body.start_date,
            end_date=body.end_date,
            rate_limit_seconds=body.rate_limit_seconds,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/match/{facility_id}")
async def match_facility(
    facility_id: str,
    body: MatchFacilityRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Manually match an EMD facility to a property."""
    svc = EMDService(db)
    try:
        facility = await svc.match_facility_to_property(
            facility_id=facility_id,
            property_id=body.property_id,
            organization_id=ctx.organization_id,
        )
        return {"matched": True, "facility_id": facility.id, "property_id": body.property_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/auto-match")
async def auto_match_facilities(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Auto-match unmatched EMD facilities to properties by address."""
    svc = EMDService(db)
    result = await svc.auto_match_facilities(ctx.organization_id)
    return result


@router.get("/leads", response_model=list[EMDLeadResponse])
async def get_leads(
    min_violations: int = Query(3),
    days: int = Query(365),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get high-violation facilities for lead generation."""
    svc = EMDService(db)
    leads = await svc.get_high_violation_facilities(
        min_violations=min_violations, days=days
    )
    return [EMDLeadResponse(**lead) for lead in leads]


@router.get("/property/{property_id}/inspections", response_model=list[EMDInspectionResponse])
async def get_property_inspections(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get inspections for a matched property."""
    svc = EMDService(db)
    inspections = await svc.get_property_inspections(property_id)
    return [EMDInspectionResponse.model_validate(i) for i in inspections]


@router.post("/facilities/{facility_id}/sync-equipment")
async def sync_equipment_to_bow(
    facility_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Sync EMD equipment data to matched property's primary BOW."""
    svc = EMDService(db)
    result = await svc.sync_equipment_to_bow(facility_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Facility not matched or no equipment data",
        )
    return result


@router.get("/backfill-status")
async def get_backfill_status(
    ctx: OrgUserContext = Depends(get_current_org_user),
):
    """Get the current EMD backfill scraper status."""
    import json
    status_file = "/tmp/emd_backfill_status.json"
    try:
        with open(status_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"state": "idle"}
