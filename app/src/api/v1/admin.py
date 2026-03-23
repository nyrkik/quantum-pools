"""Admin endpoints — platform admin operations."""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext, require_roles, OrgRole
from src.models.scraper_run import ScraperRun
from src.models.emd_facility import EMDFacility
from src.models.emd_inspection import EMDInspection
from src.models.emd_violation import EMDViolation
from src.models.property import Property
from src.models.customer import Customer
from src.models.agent_message import AgentMessage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/scraper-runs")
async def list_scraper_runs(
    limit: int = Query(20, ge=1, le=100),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """List recent scraper runs."""
    result = await db.execute(
        select(ScraperRun).order_by(desc(ScraperRun.started_at)).limit(limit)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "days_scraped": r.days_scraped,
            "inspections_found": r.inspections_found,
            "inspections_new": r.inspections_new,
            "pdfs_downloaded": r.pdfs_downloaded,
            "errors": r.errors,
            "duration_seconds": r.duration_seconds,
            "email_sent": r.email_sent,
        }
        for r in runs
    ]


@router.get("/emd-stats")
async def get_emd_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """EMD database statistics."""
    facilities = (await db.execute(select(func.count(EMDFacility.id)))).scalar()
    inspections = (await db.execute(select(func.count(EMDInspection.id)))).scalar()
    violations = (await db.execute(select(func.count(EMDViolation.id)))).scalar()

    latest = (await db.execute(
        select(EMDInspection.inspection_date)
        .order_by(desc(EMDInspection.inspection_date))
        .limit(1)
    )).scalar()

    last_run = (await db.execute(
        select(ScraperRun)
        .where(ScraperRun.status == "success")
        .order_by(desc(ScraperRun.started_at))
        .limit(1)
    )).scalar_one_or_none()

    return {
        "facilities": facilities,
        "inspections": inspections,
        "violations": violations,
        "latest_inspection_date": latest.isoformat() if latest else None,
        "last_successful_run": last_run.started_at.isoformat() if last_run else None,
        "matched": (await db.execute(select(func.count(EMDFacility.id)).where(EMDFacility.matched_property_id.isnot(None)))).scalar(),
        "unmatched": (await db.execute(select(func.count(EMDFacility.id)).where(EMDFacility.matched_property_id.is_(None)))).scalar(),
    }


@router.get("/emd-unmatched")
async def list_unmatched_facilities(
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """List EMD facilities not yet matched to a property."""
    result = await db.execute(
        select(EMDFacility)
        .where(EMDFacility.matched_property_id.is_(None))
        .order_by(EMDFacility.name)
        .limit(limit)
    )
    facilities = result.scalars().all()

    # Get inspection counts
    insp_counts = {}
    if facilities:
        fac_ids = [f.id for f in facilities]
        count_result = await db.execute(
            select(EMDInspection.facility_id, func.count(EMDInspection.id))
            .where(EMDInspection.facility_id.in_(fac_ids))
            .group_by(EMDInspection.facility_id)
        )
        insp_counts = {row[0]: row[1] for row in count_result.all()}

    return [
        {
            "id": f.id,
            "name": f.name,
            "street_address": f.street_address,
            "city": f.city,
            "facility_type": f.facility_type,
            "inspections": insp_counts.get(f.id, 0),
        }
        for f in facilities
    ]


@router.get("/properties-for-match")
async def list_properties_for_match(
    search: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """List properties for manual EMD matching."""
    query = (
        select(Property, Customer)
        .join(Customer, Property.customer_id == Customer.id)
        .where(Property.organization_id == ctx.organization_id)
        .order_by(Customer.first_name)
    )
    if search:
        q = f"%{search}%"
        query = query.where(
            Property.address.ilike(q) | Customer.first_name.ilike(q) | Customer.company_name.ilike(q)
        )
    result = await db.execute(query.limit(50))
    return [
        {
            "property_id": prop.id,
            "address": prop.full_address,
            "customer_name": cust.display_name_col,
            "emd_fa_number": prop.emd_fa_number,
        }
        for prop, cust in result.all()
    ]


class ManualMatchBody(BaseModel):
    facility_id: str
    property_id: str


@router.post("/emd-match")
async def manual_match_facility(
    body: ManualMatchBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Manually match an EMD facility to a property."""
    from src.services.emd.service import EMDService
    svc = EMDService(db)
    try:
        facility = await svc.match_facility(body.facility_id, body.property_id, ctx.organization_id)
        # Copy FA number to property if not already set
        prop = (await db.execute(select(Property).where(Property.id == body.property_id))).scalar_one_or_none()
        if prop and not prop.emd_fa_number and facility.facility_id:
            prop.emd_fa_number = facility.facility_id
        await db.flush()
        return {"matched": True, "facility_name": facility.name, "property_id": body.property_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/emd-unmatch/{facility_id}")
async def unmatch_facility(
    facility_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Remove match between EMD facility and property."""
    result = await db.execute(select(EMDFacility).where(EMDFacility.id == facility_id))
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    facility.matched_property_id = None
    facility.matched_at = None
    await db.flush()
    return {"unmatched": True}


# --- Agent Message Log ---

@router.get("/agent-messages")
async def list_agent_messages(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """List recent agent messages."""
    query = select(AgentMessage).order_by(desc(AgentMessage.received_at)).limit(limit)
    if status:
        query = query.where(AgentMessage.status == status)
    result = await db.execute(query)
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "direction": m.direction,
            "from_email": m.from_email,
            "to_email": m.to_email,
            "subject": m.subject,
            "category": m.category,
            "urgency": m.urgency,
            "status": m.status,
            "customer_name": m.customer_name,
            "draft_response": m.draft_response,
            "final_response": m.final_response,
            "approved_by": m.approved_by,
            "received_at": m.received_at.isoformat() if m.received_at else None,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        }
        for m in messages
    ]


# --- Twilio SMS Webhook ---

from fastapi import Request, Response

@router.post("/twilio-webhook")
async def twilio_sms_webhook(request: Request):
    """Handle incoming SMS from Twilio (approval replies)."""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "")

    if from_number and body:
        from src.services.customer_agent import handle_sms_reply
        import asyncio
        asyncio.create_task(handle_sms_reply(from_number, body))

    # Return empty TwiML to acknowledge
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
