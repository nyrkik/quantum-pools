"""EMD inspection intelligence endpoints — tier-aware access."""

import os
import uuid
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, require_feature, OrgUserContext
from src.models.organization_user import OrgRole
from src.models.inspection_lookup import InspectionLookup
from src.schemas.inspection import (
    InspectionFacilityListResponse,
    InspectionFacilityDetailResponse,
    InspectionResponse,
    InspectionDetailResponse,
    InspectionViolationResponse,
    InspectionEquipmentResponse,
    InspectionLeadResponse,
    ScrapeRequest,
    MatchFacilityRequest,
)
from src.services.inspection.service import InspectionService
from src.services.feature_service import FeatureService

router = APIRouter(prefix="/inspections", tags=["inspections"], dependencies=[Depends(require_feature("inspection_intelligence"))])

LOOKUP_DURATION_DAYS = 30
LOOKUP_PRICE_CENTS = 99


async def _get_emd_tier(ctx: OrgUserContext, db: AsyncSession) -> str | None:
    """Get the org's EMD subscription tier."""
    svc = FeatureService(db)
    return await svc.get_org_emd_tier(ctx.organization_id)


async def _has_facility_access(
    ctx: OrgUserContext, db: AsyncSession, facility_id: str, tier: str | None
) -> bool:
    """Check if org can view full detail for a facility."""
    if tier == "full_research":
        return True

    # Check if facility is matched to org's property
    from src.models.inspection_facility import InspectionFacility
    result = await db.execute(
        select(InspectionFacility).where(
            InspectionFacility.id == facility_id,
            InspectionFacility.organization_id == ctx.organization_id,
        )
    )
    if result.scalar_one_or_none():
        return True

    # Check for active single lookup
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(InspectionLookup).where(
            InspectionLookup.organization_id == ctx.organization_id,
            InspectionLookup.facility_id == facility_id,
            InspectionLookup.expires_at > now,
        )
    )
    if result.scalar_one_or_none():
        return True

    return False


# --- Dashboard ---

@router.get("/dashboard")
async def get_dashboard(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get operations dashboard. Available to all EMD tiers (shows matched-only data)."""
    svc = InspectionService(db)
    return await svc.get_dashboard()


# --- Facility list ---

@router.get("/facilities", response_model=list[InspectionFacilityListResponse])
async def list_facilities(
    search: Optional[str] = Query(None),
    matched_only: bool = Query(False),
    sort: str = Query("name"),
    limit: int = Query(2000, le=5000),
    offset: int = Query(0),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List EMD facilities. my_inspections tier only sees matched facilities."""
    tier = await _get_emd_tier(ctx, db)

    # my_inspections tier: force matched_only
    if tier != "full_research":
        matched_only = True

    svc = InspectionService(db)
    facilities, total = await svc.list_facilities(
        search=search, matched_only=matched_only, limit=limit, offset=offset, sort=sort
    )
    return [InspectionFacilityListResponse(**f) for f in facilities]


# --- Search (available to all tiers, returns redacted results for non-accessible) ---

@router.get("/search")
async def search_facilities(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, le=50),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Search all facilities. Returns redacted results for facilities the org can't access.
    Used for single-lookup cart building.
    """
    tier = await _get_emd_tier(ctx, db)
    svc = InspectionService(db)
    facilities, _ = await svc.list_facilities(search=q, limit=limit, offset=0, sort="name")

    # Get active lookups for this org
    now = datetime.now(timezone.utc)
    lookup_result = await db.execute(
        select(InspectionLookup.facility_id).where(
            InspectionLookup.organization_id == ctx.organization_id,
            InspectionLookup.expires_at > now,
        )
    )
    active_lookup_ids = set(lookup_result.scalars().all())

    results = []
    for f in facilities:
        is_matched = f["matched_property_id"] is not None
        has_lookup = f["id"] in active_lookup_ids
        has_access = tier == "full_research" or is_matched or has_lookup

        if has_access:
            results.append({**f, "redacted": False, "has_lookup": has_lookup})
        else:
            # Redacted: show name + violation count + partial address, hide detail
            results.append({
                "id": f["id"],
                "name": f["name"],
                "city": f["city"],
                "facility_type": f["facility_type"],
                "program_identifier": f.get("program_identifier"),
                "total_violations": f["total_violations"],
                "total_inspections": f["total_inspections"],
                "last_inspection_date": f["last_inspection_date"],
                "is_closed": f["is_closed"],
                "redacted": True,
                "has_lookup": False,
                # Redact street address
                "street_address": None,
                "facility_id": None,
                "matched_property_id": None,
                "closure_reasons": [],
            })

    return results


# --- Facility detail ---

@router.get("/facilities/{facility_id}")
async def get_facility_detail(
    facility_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get facility detail. Requires full_research, matched facility, or active lookup."""
    tier = await _get_emd_tier(ctx, db)
    has_access = await _has_facility_access(ctx, db, facility_id, tier)

    svc = InspectionService(db)
    detail = await svc.get_facility_detail(facility_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found")

    if not has_access:
        # Return tease data
        facility = detail["facility"]
        return {
            "id": facility.id,
            "name": facility.name,
            "city": facility.city,
            "facility_type": facility.facility_type,
            "total_inspections": detail["total_inspections"],
            "total_violations": detail["total_violations"],
            "last_inspection_date": detail["last_inspection_date"],
            "redacted": True,
            "unlock_price_cents": LOOKUP_PRICE_CENTS,
        }

    facility = detail["facility"]
    resp = InspectionFacilityDetailResponse(
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
        inspections=[InspectionDetailResponse.model_validate(i) for i in detail["inspections"]],
        total_inspections=detail["total_inspections"],
        total_violations=detail["total_violations"],
        last_inspection_date=detail["last_inspection_date"],
        matched_property_address=detail["matched_property_address"],
        matched_customer_name=detail["matched_customer_name"],
    )
    result = resp.model_dump()
    result["programs"] = detail.get("programs", [])
    result["matched_customer_id"] = detail.get("matched_customer_id")
    result["matched_bow_names"] = detail.get("matched_bow_names", {})
    return result


@router.get("/facilities/{facility_id}/inspections", response_model=list[InspectionResponse])
async def get_facility_inspections(
    facility_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all inspections for a facility. Requires access."""
    tier = await _get_emd_tier(ctx, db)
    if not await _has_facility_access(ctx, db, facility_id, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error": "facility_not_accessible",
            "message": "Purchase a single lookup or upgrade to Full Research to access this facility.",
        })
    svc = InspectionService(db)
    inspections = await svc.get_facility_inspections(facility_id)
    return [InspectionResponse.model_validate(i) for i in inspections]


@router.get("/facilities/{facility_id}/equipment", response_model=Optional[InspectionEquipmentResponse])
async def get_facility_equipment(
    facility_id: str,
    permit_id: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get latest equipment data for a facility, optionally filtered by permit_id. Requires access."""
    tier = await _get_emd_tier(ctx, db)
    if not await _has_facility_access(ctx, db, facility_id, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error": "facility_not_accessible",
            "message": "Purchase a single lookup or upgrade to Full Research to access this facility.",
        })
    svc = InspectionService(db)
    equipment = await svc.get_facility_equipment(facility_id, permit_id=permit_id)
    if not equipment:
        return None
    return InspectionEquipmentResponse.model_validate(equipment)


# --- Single Lookups ---

@router.get("/lookups")
async def get_active_lookups(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get active single lookups for this org."""
    from src.models.inspection_facility import InspectionFacility

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(InspectionLookup, InspectionFacility)
        .join(InspectionFacility, InspectionLookup.facility_id == InspectionFacility.id)
        .where(
            InspectionLookup.organization_id == ctx.organization_id,
            InspectionLookup.expires_at > now,
        )
        .order_by(InspectionLookup.purchased_at.desc())
    )
    rows = result.all()

    return [
        {
            "id": lookup.id,
            "facility_id": facility.id,
            "facility_name": facility.name,
            "city": facility.city,
            "purchased_at": lookup.purchased_at.isoformat(),
            "expires_at": lookup.expires_at.isoformat(),
            "days_remaining": max(0, (lookup.expires_at - now).days),
        }
        for lookup, facility in rows
    ]


@router.post("/lookups/purchase")
async def purchase_lookups(
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Purchase single lookups for multiple facilities.
    Body: {"facility_ids": ["id1", "id2", ...]}
    Returns created lookups. Stripe integration TBD — currently creates records directly.
    """
    facility_ids = body.get("facility_ids", [])
    if not facility_ids:
        raise HTTPException(status_code=400, detail="No facility IDs provided")
    if len(facility_ids) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 facilities per purchase")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=LOOKUP_DURATION_DAYS)

    # Validate facilities exist
    from src.models.inspection_facility import InspectionFacility
    result = await db.execute(
        select(InspectionFacility.id).where(InspectionFacility.id.in_(facility_ids))
    )
    valid_ids = set(result.scalars().all())
    invalid = set(facility_ids) - valid_ids
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid facility IDs: {', '.join(invalid)}")

    # Check for existing active lookups (don't double-charge)
    result = await db.execute(
        select(InspectionLookup.facility_id).where(
            InspectionLookup.organization_id == ctx.organization_id,
            InspectionLookup.facility_id.in_(facility_ids),
            InspectionLookup.expires_at > now,
        )
    )
    already_active = set(result.scalars().all())

    created = []
    for fid in facility_ids:
        if fid in already_active:
            continue
        lookup = InspectionLookup(
            id=str(uuid.uuid4()),
            organization_id=ctx.organization_id,
            facility_id=fid,
            price_cents=LOOKUP_PRICE_CENTS,
            purchased_at=now,
            expires_at=expires_at,
        )
        db.add(lookup)
        created.append(fid)

    await db.flush()

    total_cents = len(created) * LOOKUP_PRICE_CENTS

    return {
        "purchased": len(created),
        "already_active": len(already_active),
        "total_cents": total_cents,
        "expires_at": expires_at.isoformat(),
        "facility_ids": created,
    }


# --- Admin operations ---

@router.post("/scrape")
async def trigger_scrape(
    body: ScrapeRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a scrape for a date range (admin only)."""
    svc = InspectionService(db)
    try:
        result = await svc.scrape_date_range(
            start_date=body.start_date,
            end_date=body.end_date,
            rate_limit_seconds=body.rate_limit_seconds,
        )
        if result.get("new_facilities", 0) > 0:
            match_result = await svc.auto_match_facilities(ctx.organization_id)
            result["auto_matched"] = match_result.get("matched", 0)
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
    svc = InspectionService(db)
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
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Auto-match unmatched EMD facilities to properties by address."""
    svc = InspectionService(db)
    result = await svc.auto_match_facilities(ctx.organization_id)
    return result


# --- User-facing EMD matching ---

@router.get("/my-properties")
async def get_my_properties_emd_status(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get EMD match status for all commercial properties."""
    svc = InspectionService(db)
    return await svc.get_org_properties_emd_status(ctx.organization_id)


@router.get("/suggest-matches/{property_id}")
async def suggest_emd_matches(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Suggest top EMD facility matches for a property (redacted — no inspection details)."""
    svc = InspectionService(db)
    return await svc.suggest_matches(property_id, ctx.organization_id)


from pydantic import BaseModel as _BaseModel

class _ConfirmMatchBody(_BaseModel):
    property_id: str
    facility_id: str

@router.post("/confirm-match")
async def confirm_emd_match(
    body: _ConfirmMatchBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """User confirms an EMD facility match to their property."""
    svc = InspectionService(db)

    # Verify property belongs to org
    from src.models.property import Property
    prop = (await db.execute(
        select(Property).where(Property.id == body.property_id, Property.organization_id == ctx.organization_id)
    )).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check facility isn't already matched to a different property
    from src.models.inspection_facility import InspectionFacility
    facility = (await db.execute(
        select(InspectionFacility).where(InspectionFacility.id == body.facility_id)
    )).scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.matched_property_id and facility.matched_property_id != body.property_id:
        raise HTTPException(status_code=400, detail="This facility is already matched to another property")

    try:
        await svc.match_facility_to_property(body.facility_id, body.property_id, ctx.organization_id)
        # Copy FA number
        if facility.facility_id and not prop.emd_fa_number:
            prop.emd_fa_number = facility.facility_id
        await db.flush()
        return {"matched": True, "facility_name": facility.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reject-match/{property_id}")
async def reject_emd_match(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """User rejects an EMD match — unlinks and clears FA/PR numbers."""
    svc = InspectionService(db)
    await svc.unmatch_property(property_id, ctx.organization_id)
    return {"unmatched": True}


# --- Leads (requires full_research) ---

@router.get("/leads", response_model=list[InspectionLeadResponse])
async def get_leads(
    min_violations: int = Query(3),
    days: int = Query(365),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get high-violation facilities for lead generation. Requires full_research tier."""
    tier = await _get_emd_tier(ctx, db)
    if tier != "full_research":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error": "tier_required",
            "required_tier": "full_research",
            "message": "Upgrade to Full Research to access lead generation.",
        })
    svc = InspectionService(db)
    leads = await svc.get_high_violation_facilities(min_violations=min_violations, days=days)
    return [InspectionLeadResponse(**lead) for lead in leads]


# --- Property inspections ---

@router.get("/property/{property_id}/inspections", response_model=list[InspectionResponse])
async def get_property_inspections(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get inspections for a matched property."""
    svc = InspectionService(db)
    inspections = await svc.get_property_inspections(property_id)
    return [InspectionResponse.model_validate(i) for i in inspections]


@router.post("/facilities/{facility_id}/sync-equipment")
async def sync_equipment_to_bow(
    facility_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Sync EMD equipment data to matched property's primary WF."""
    svc = InspectionService(db)
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
    """Get the current EMD scraper health status."""
    import json
    # Try daily scraper health first, fall back to old backfill status
    for status_file in ["/tmp/emd_scraper_health.json", "/tmp/emd_backfill_status.json"]:
        try:
            with open(status_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {"state": "idle"}


@router.get("/inspections/{inspection_id}/pdf")
async def get_inspection_pdf(
    inspection_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve an inspection PDF file. Requires access to the facility."""
    from src.models.inspection import Inspection

    result = await db.execute(
        select(Inspection).where(Inspection.id == inspection_id)
    )
    inspection = result.scalar_one_or_none()
    if not inspection or not inspection.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Check access
    tier = await _get_emd_tier(ctx, db)
    if not await _has_facility_access(ctx, db, inspection.facility_id, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Facility not accessible")

    if not os.path.isabs(inspection.pdf_path):
        pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), inspection.pdf_path)
    else:
        pdf_path = inspection.pdf_path

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not on disk")

    return FileResponse(pdf_path, media_type="application/pdf")
