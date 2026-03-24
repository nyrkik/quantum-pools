"""Admin endpoints — platform admin operations."""

import os
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
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction, AgentActionComment

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

def _serialize_agent_msg(m: AgentMessage, include_body: bool = False) -> dict:
    d = {
        "id": m.id,
        "direction": m.direction,
        "from_email": m.from_email,
        "to_email": m.to_email,
        "subject": m.subject,
        "category": m.category,
        "urgency": m.urgency,
        "status": m.status,
        "matched_customer_id": m.matched_customer_id,
        "match_method": m.match_method,
        "customer_name": m.customer_name,
        "draft_response": m.draft_response,
        "final_response": m.final_response,
        "approved_by": m.approved_by,
        "notes": m.notes,
        "received_at": m.received_at.isoformat() if m.received_at else None,
        "approved_at": m.approved_at.isoformat() if m.approved_at else None,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
    }
    if include_body:
        d["body"] = m.body
    return d


@router.get("/agent-messages")
async def list_agent_messages(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    exclude_categories: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List agent messages with pagination."""
    base = select(AgentMessage).where(AgentMessage.organization_id == ctx.organization_id)
    if status:
        base = base.where(AgentMessage.status == status)
    if category:
        base = base.where(AgentMessage.category == category)
    if exclude_categories:
        excluded = [c.strip() for c in exclude_categories.split(",") if c.strip()]
        if excluded:
            base = base.where(
                AgentMessage.category.notin_(excluded) | AgentMessage.category.is_(None)
            )
    if search:
        q = f"%{search}%"
        base = base.where(
            AgentMessage.from_email.ilike(q)
            | AgentMessage.subject.ilike(q)
            | AgentMessage.customer_name.ilike(q)
        )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    result = await db.execute(base.order_by(desc(AgentMessage.received_at)).offset(offset).limit(limit))
    return {
        "items": [_serialize_agent_msg(m) for m in result.scalars().all()],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/agent-stats")
async def get_agent_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Agent message statistics."""
    from datetime import datetime, timezone, timedelta

    org_filter = AgentMessage.organization_id == ctx.organization_id
    total = (await db.execute(select(func.count(AgentMessage.id)).where(org_filter))).scalar() or 0

    status_counts = {}
    for s in ("pending", "sent", "auto_sent", "rejected", "ignored"):
        c = (await db.execute(
            select(func.count(AgentMessage.id)).where(org_filter, AgentMessage.status == s)
        )).scalar() or 0
        status_counts[s] = c

    cat_result = await db.execute(
        select(AgentMessage.category, func.count(AgentMessage.id))
        .where(org_filter, AgentMessage.category.isnot(None))
        .group_by(AgentMessage.category)
    )
    by_category = {row[0]: row[1] for row in cat_result.all()}

    urg_result = await db.execute(
        select(AgentMessage.urgency, func.count(AgentMessage.id))
        .where(org_filter, AgentMessage.urgency.isnot(None))
        .group_by(AgentMessage.urgency)
    )
    by_urgency = {row[0]: row[1] for row in urg_result.all()}

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = (await db.execute(
        select(func.count(AgentMessage.id)).where(org_filter, AgentMessage.received_at >= since_24h)
    )).scalar() or 0

    # Action item counts
    action_org = AgentAction.organization_id == ctx.organization_id
    open_actions = (await db.execute(
        select(func.count(AgentAction.id)).where(action_org, AgentAction.status.in_(("open", "in_progress")))
    )).scalar() or 0
    overdue_actions = (await db.execute(
        select(func.count(AgentAction.id)).where(
            action_org,
            AgentAction.status.in_(("open", "in_progress")),
            AgentAction.due_date < datetime.now(timezone.utc),
        )
    )).scalar() or 0

    # Avg response time for sent messages (seconds)
    from sqlalchemy import extract
    avg_result = await db.execute(
        select(func.avg(extract("epoch", AgentMessage.sent_at) - extract("epoch", AgentMessage.received_at)))
        .where(org_filter, AgentMessage.status.in_(("sent", "auto_sent")), AgentMessage.sent_at.isnot(None))
    )
    avg_response_sec = avg_result.scalar()

    # Stale pending count (> 30 min)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale_pending = (await db.execute(
        select(func.count(AgentMessage.id)).where(
            org_filter,
            AgentMessage.status == "pending",
            AgentMessage.received_at < stale_cutoff,
        )
    )).scalar() or 0

    return {
        "total": total,
        **status_counts,
        "by_category": by_category,
        "by_urgency": by_urgency,
        "recent_24h": recent,
        "open_actions": open_actions,
        "overdue_actions": overdue_actions,
        "avg_response_seconds": round(avg_response_sec) if avg_response_sec else None,
        "stale_pending": stale_pending,
    }


def _serialize_action(a: AgentAction, include_comments: bool = False) -> dict:
    d = {
        "id": a.id,
        "agent_message_id": a.agent_message_id,
        "action_type": a.action_type,
        "description": a.description,
        "assigned_to": a.assigned_to,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "status": a.status,
        "notes": a.notes,
        "customer_name": a.customer_name,
        "property_address": a.property_address,
        "created_by": a.created_by,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
    if include_comments and hasattr(a, "comments") and a.comments:
        d["comments"] = [
            {"id": c.id, "author": c.author, "text": c.text, "created_at": c.created_at.isoformat()}
            for c in a.comments
        ]
    return d


@router.get("/agent-messages/{message_id}")
async def get_agent_message(
    message_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get full agent message detail."""
    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    d = _serialize_agent_msg(msg, include_body=True)
    # Include actions
    actions_result = await db.execute(
        select(AgentAction).where(AgentAction.agent_message_id == message_id, AgentAction.organization_id == ctx.organization_id).order_by(AgentAction.created_at)
    )
    d["actions"] = [_serialize_action(a) for a in actions_result.scalars().all()]
    # Response time
    if msg.sent_at and msg.received_at:
        d["response_time_seconds"] = int((msg.sent_at - msg.received_at).total_seconds())
    else:
        d["response_time_seconds"] = None
    # Waiting time for pending
    if msg.status == "pending" and msg.received_at:
        from datetime import datetime, timezone
        d["waiting_seconds"] = int((datetime.now(timezone.utc) - msg.received_at).total_seconds())
    else:
        d["waiting_seconds"] = None
    return d


class ApproveBody(BaseModel):
    response_text: Optional[str] = None


class ReviseDraftBody(BaseModel):
    draft: str
    instruction: str


@router.post("/agent-messages/{message_id}/approve")
async def approve_agent_message(
    message_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Approve and send an agent message from the dashboard."""
    from datetime import datetime, timezone
    from src.services.customer_agent import send_email_response

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Cannot approve message with status '{msg.status}'")

    response_text = body.response_text or msg.draft_response
    if not response_text:
        raise HTTPException(status_code=400, detail="No response text provided")

    success = await send_email_response(msg.from_email, msg.subject or "", response_text)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    now = datetime.now(timezone.utc)
    msg.status = "sent"
    msg.final_response = response_text
    msg.approved_by = f"{ctx.user.first_name} {ctx.user.last_name}"
    msg.approved_at = now
    msg.sent_at = now
    await db.commit()

    # Save discovered contact info to customer record
    from src.services.customer_agent import save_discovered_contact
    await save_discovered_contact(message_id)

    return {"sent": True, "to": msg.from_email}


@router.post("/agent-messages/{message_id}/reject")
async def reject_agent_message(
    message_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Reject an agent message."""
    from datetime import datetime, timezone

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Cannot reject message with status '{msg.status}'")

    msg.status = "rejected"
    msg.approved_by = f"{ctx.user.first_name} {ctx.user.last_name}"
    msg.approved_at = datetime.now(timezone.utc)
    await db.commit()

    return {"rejected": True}


@router.post("/agent-messages/{message_id}/dismiss")
async def dismiss_agent_message(
    message_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a message — no reply needed, keeps action items open."""
    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Cannot dismiss message with status '{msg.status}'")

    msg.status = "ignored"
    msg.notes = (msg.notes or "") + "\nDismissed by " + f"{ctx.user.first_name} {ctx.user.last_name}"
    msg.notes = msg.notes.strip()

    await db.commit()
    return {"dismissed": True}


@router.delete("/agent-messages/{message_id}")
async def delete_agent_message(
    message_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message and its actions entirely — for test/spam that got through."""
    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Delete associated actions first
    actions_result = await db.execute(
        select(AgentAction).where(AgentAction.agent_message_id == message_id, AgentAction.organization_id == ctx.organization_id)
    )
    for action in actions_result.scalars().all():
        await db.delete(action)

    await db.delete(msg)
    await db.commit()
    return {"deleted": True}


@router.get("/client-search")
async def search_clients(
    q: str = Query(..., min_length=2),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Search customers + properties for autocomplete."""
    search = f"%{q}%"
    result = await db.execute(
        select(Customer, Property)
        .join(Property, Customer.id == Property.customer_id)
        .where(
            Property.organization_id == ctx.organization_id,
            Customer.is_active == True,
        )
        .where(
            Customer.first_name.ilike(search)
            | Customer.last_name.ilike(search)
            | Customer.company_name.ilike(search)
            | Customer.display_name_col.ilike(search)
            | Property.address.ilike(search)
            | Property.name.ilike(search)
        )
        .order_by(Customer.first_name)
        .limit(10)
    )
    return [
        {
            "customer_name": cust.display_name,
            "property_address": prop.full_address,
            "property_name": prop.name,
        }
        for cust, prop in result.all()
    ]


# --- Conversation Threads ---

@router.get("/agent-threads")
async def list_threads(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    exclude_spam: bool = Query(True),
    exclude_ignored: bool = Query(False),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List conversation threads."""
    base = select(AgentThread).where(AgentThread.organization_id == ctx.organization_id)
    if status == "pending":
        base = base.where(AgentThread.has_pending == True)
    elif status == "handled":
        base = base.where(AgentThread.status == "handled")
    elif status == "ignored":
        base = base.where(AgentThread.status == "ignored")
    if exclude_spam:
        base = base.where(AgentThread.category.notin_(["spam", "auto_reply"]) | AgentThread.category.is_(None))
    if exclude_ignored:
        base = base.where(AgentThread.status != "ignored")
    if search:
        q = f"%{search}%"
        base = base.where(
            AgentThread.contact_email.ilike(q)
            | AgentThread.subject.ilike(q)
            | AgentThread.customer_name.ilike(q)
        )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    result = await db.execute(
        base.order_by(
            desc(AgentThread.has_pending),
            desc(AgentThread.last_message_at),
        ).offset(offset).limit(limit)
    )
    threads = result.scalars().all()
    return {
        "items": [
            {
                "id": t.id,
                "contact_email": t.contact_email,
                "subject": t.subject,
                "customer_name": t.customer_name,
                "matched_customer_id": t.matched_customer_id,
                "status": t.status,
                "urgency": t.urgency,
                "category": t.category,
                "message_count": t.message_count,
                "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
                "last_direction": t.last_direction,
                "last_snippet": t.last_snippet,
                "has_pending": t.has_pending,
                "has_open_actions": t.has_open_actions,
            }
            for t in threads
        ],
        "total": total,
    }


@router.get("/agent-threads/stats")
async def get_thread_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Thread-level stats."""
    from datetime import datetime, timezone, timedelta

    thread_org = AgentThread.organization_id == ctx.organization_id
    total = (await db.execute(select(func.count(AgentThread.id)).where(thread_org))).scalar() or 0
    pending = (await db.execute(
        select(func.count(AgentThread.id)).where(thread_org, AgentThread.has_pending == True)
    )).scalar() or 0

    # Stale: pending threads where last_message_at > 30 min ago
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale = (await db.execute(
        select(func.count(AgentThread.id)).where(
            thread_org,
            AgentThread.has_pending == True,
            AgentThread.last_message_at < stale_cutoff,
        )
    )).scalar() or 0

    open_actions = (await db.execute(
        select(func.count(AgentAction.id)).where(AgentAction.organization_id == ctx.organization_id, AgentAction.status.in_(("open", "in_progress")))
    )).scalar() or 0

    return {
        "total": total,
        "pending": pending,
        "stale_pending": stale,
        "open_actions": open_actions,
    }


@router.get("/agent-threads/{thread_id}")
async def get_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get thread with full conversation timeline."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Get all messages in thread
    msgs_result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == ctx.organization_id)
        .order_by(AgentMessage.received_at)
    )
    messages = msgs_result.scalars().all()

    # Build conversation timeline — include outbound from final_response on inbound msgs
    timeline = []
    for m in messages:
        timeline.append({
            "id": m.id,
            "direction": m.direction,
            "from_email": m.from_email,
            "to_email": m.to_email,
            "subject": m.subject,
            "body": m.body,
            "category": m.category,
            "urgency": m.urgency,
            "status": m.status,
            "draft_response": m.draft_response if m.status == "pending" else None,
            "received_at": m.received_at.isoformat() if m.received_at else None,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            "approved_by": m.approved_by,
        })
        # If inbound message was sent and has final_response, add outbound bubble
        # (for historical messages before we started creating outbound rows)
        if m.direction == "inbound" and m.final_response and m.status in ("sent", "auto_sent"):
            # Check if there's already an outbound message right after
            has_outbound = any(
                om.direction == "outbound" and om.sent_at and m.sent_at
                and abs((om.sent_at - m.sent_at).total_seconds()) < 60
                for om in messages
            )
            if not has_outbound:
                timeline.append({
                    "id": f"{m.id}-reply",
                    "direction": "outbound",
                    "from_email": os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com"),
                    "to_email": m.from_email,
                    "subject": f"Re: {m.subject}" if m.subject else None,
                    "body": m.final_response,
                    "category": None,
                    "urgency": None,
                    "status": "sent",
                    "draft_response": None,
                    "received_at": m.sent_at.isoformat() if m.sent_at else m.received_at.isoformat(),
                    "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                    "approved_by": m.approved_by,
                })

    # Get actions for this thread
    actions_result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(AgentAction.thread_id == thread_id, AgentAction.organization_id == ctx.organization_id)
        .order_by(AgentAction.created_at)
    )
    actions = [_serialize_action(a, include_comments=True) for a in actions_result.scalars().all()]

    return {
        "id": thread.id,
        "contact_email": thread.contact_email,
        "subject": thread.subject,
        "customer_name": thread.customer_name,
        "matched_customer_id": thread.matched_customer_id,
        "property_address": thread.property_address,
        "status": thread.status,
        "urgency": thread.urgency,
        "category": thread.category,
        "message_count": thread.message_count,
        "has_pending": thread.has_pending,
        "has_open_actions": thread.has_open_actions,
        "timeline": timeline,
        "actions": actions,
    }


@router.post("/agent-threads/{thread_id}/approve")
async def approve_thread(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Approve the latest pending message in a thread."""
    from datetime import datetime, timezone
    from src.services.customer_agent import send_email_response, update_thread_status

    # Find the latest pending inbound message in this thread
    result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == ctx.organization_id, AgentMessage.status == "pending", AgentMessage.direction == "inbound")
        .order_by(desc(AgentMessage.received_at))
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=400, detail="No pending message in this thread")

    response_text = body.response_text or msg.draft_response
    if not response_text:
        raise HTTPException(status_code=400, detail="No response text provided")

    success = await send_email_response(msg.from_email, msg.subject or "", response_text)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    now = datetime.now(timezone.utc)
    msg.status = "sent"
    msg.final_response = response_text
    msg.approved_by = f"{ctx.user.first_name} {ctx.user.last_name}"
    msg.approved_at = now
    msg.sent_at = now

    # Create outbound message row
    outbound = AgentMessage(
        organization_id=ctx.organization_id,
        direction="outbound",
        from_email=os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com"),
        to_email=msg.from_email,
        subject=f"Re: {msg.subject}" if msg.subject and not msg.subject.startswith("Re:") else msg.subject,
        body=response_text,
        status="sent",
        thread_id=thread_id,
        matched_customer_id=msg.matched_customer_id,
        customer_name=msg.customer_name,
        sent_at=now,
        received_at=now,
    )
    db.add(outbound)
    await db.commit()

    await update_thread_status(thread_id)

    # Save discovered contact
    from src.services.customer_agent import save_discovered_contact
    await save_discovered_contact(msg.id)

    return {"sent": True, "to": msg.from_email}


@router.post("/agent-threads/{thread_id}/dismiss")
async def dismiss_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss all pending messages in a thread."""
    from src.services.customer_agent import update_thread_status

    result = await db.execute(
        select(AgentMessage).where(
            AgentMessage.thread_id == thread_id,
            AgentMessage.organization_id == ctx.organization_id,
            AgentMessage.status == "pending",
        )
    )
    for msg in result.scalars().all():
        msg.status = "ignored"
        msg.notes = (msg.notes or "") + f"\nDismissed by {ctx.user.first_name} {ctx.user.last_name}"
        msg.notes = msg.notes.strip()
    await db.commit()
    await update_thread_status(thread_id)
    return {"dismissed": True}


@router.post("/agent-threads/{thread_id}/send-followup")
async def send_thread_followup(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up in a thread."""
    from datetime import datetime, timezone
    from src.services.customer_agent import send_email_response, update_thread_status

    thread = (await db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id))).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    response_text = body.response_text
    if not response_text:
        raise HTTPException(status_code=400, detail="No response text")

    success = await send_email_response(thread.contact_email, thread.subject or "", response_text)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send")

    now = datetime.now(timezone.utc)
    outbound = AgentMessage(
        organization_id=ctx.organization_id,
        direction="outbound",
        from_email=os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com"),
        to_email=thread.contact_email,
        subject=f"Re: {thread.subject}" if thread.subject and not thread.subject.startswith("Re:") else thread.subject,
        body=response_text,
        status="sent",
        thread_id=thread_id,
        matched_customer_id=thread.matched_customer_id,
        customer_name=thread.customer_name,
        sent_at=now,
        received_at=now,
    )
    db.add(outbound)
    await db.commit()
    await update_thread_status(thread_id)

    return {"sent": True, "to": thread.contact_email}


@router.post("/agent-threads/{thread_id}/revise-draft")
async def revise_thread_draft(
    thread_id: str,
    body: ReviseDraftBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Revise the draft on the latest pending message in a thread."""
    import anthropic, os

    thread = (await db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id))).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    prompt = f"""Revise this email draft based on the instruction below.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}

Current draft:
{body.draft}

Instruction: {body.instruction}

Rules:
- Apply the instruction to the draft
- Keep the same general structure and signature
- Never admit fault or accept blame
- Return ONLY the revised email text, nothing else"""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"draft": response.content[0].text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")


@router.post("/agent-threads/{thread_id}/draft-followup")
async def draft_thread_followup(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Draft a follow-up for a thread using full conversation context."""
    import anthropic, os
    from sqlalchemy.orm import selectinload

    thread = (await db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id))).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Get conversation
    msgs = (await db.execute(
        select(AgentMessage).where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == ctx.organization_id).order_by(AgentMessage.received_at)
    )).scalars().all()

    convo = ""
    for m in msgs:
        who = "Client" if m.direction == "inbound" else "Us"
        convo += f"\n[{who}]: {(m.body or m.final_response or '')[:300]}"

    # Get actions + comments
    actions_result = await db.execute(
        select(AgentAction).options(selectinload(AgentAction.comments)).where(AgentAction.thread_id == thread_id, AgentAction.organization_id == ctx.organization_id)
    )
    actions_ctx = ""
    for a in actions_result.scalars().all():
        actions_ctx += f"\n- [{a.status}] {a.action_type}: {a.description}"
        if a.comments:
            for c in a.comments:
                actions_ctx += f"\n  {c.author}: {c.text}"

    prompt = f"""Draft a follow-up email for a pool service company.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Jobs and comments:{actions_ctx or ' None'}

Draft a follow-up email continuing this conversation. Reference what's been discussed and any work done.

Rules:
- Professional, friendly tone
- Never admit fault
- Keep it concise — 2-4 sentences
- End with: Best,\\nThe {os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")} Team\\n{os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")}

Return ONLY the email body text."""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"draft": response.content[0].text.strip(), "to": thread.contact_email, "subject": thread.subject}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")


# --- Agent Actions ---

@router.get("/agent-actions")
async def list_agent_actions(
    status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List jobs — both email-linked and standalone."""
    query = select(AgentAction, AgentMessage).outerjoin(
        AgentMessage, AgentAction.agent_message_id == AgentMessage.id
    ).where(AgentAction.organization_id == ctx.organization_id).order_by(
        # Open first, then by due date
        desc(AgentAction.status.in_(("open", "in_progress"))),
        AgentAction.due_date.asc().nulls_last(),
    ).limit(limit)
    if status:
        query = query.where(AgentAction.status == status)
    if assigned_to:
        query = query.where(AgentAction.assigned_to == assigned_to)
    if action_type:
        query = query.where(AgentAction.action_type == action_type)
    result = await db.execute(query)
    rows = result.all()
    items = []
    for action, msg in rows:
        d = _serialize_action(action)
        # Use message data if linked, otherwise use action's own fields
        if msg:
            d["from_email"] = msg.from_email
            d["customer_name"] = msg.customer_name or action.customer_name
            d["subject"] = msg.subject
        else:
            d["from_email"] = None
            d["customer_name"] = action.customer_name
            d["subject"] = None
        d["property_address"] = action.property_address
        items.append(d)
    return items


class CreateActionBody(BaseModel):
    agent_message_id: Optional[str] = None
    action_type: str
    description: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    customer_name: Optional[str] = None
    property_address: Optional[str] = None


@router.post("/agent-actions")
async def create_agent_action(
    body: CreateActionBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create an action item — standalone or linked to a message."""
    from datetime import datetime, timezone
    due = datetime.fromisoformat(body.due_date) if body.due_date else None
    action = AgentAction(
        organization_id=ctx.organization_id,
        agent_message_id=body.agent_message_id or None,
        action_type=body.action_type,
        description=body.description,
        assigned_to=body.assigned_to,
        due_date=due,
        customer_name=body.customer_name,
        property_address=body.property_address,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
        status="open",
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)
    return _serialize_action(action)


class UpdateActionBody(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


@router.put("/agent-actions/{action_id}")
async def update_agent_action(
    action_id: str,
    body: UpdateActionBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update an action item (status, assignment, etc)."""
    from datetime import datetime, timezone
    result = await db.execute(select(AgentAction).where(AgentAction.id == action_id, AgentAction.organization_id == ctx.organization_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    was_not_done = action.status != "done"

    if body.status is not None:
        action.status = body.status
        if body.status == "done":
            action.completed_at = datetime.now(timezone.utc)
        elif body.status in ("open", "in_progress"):
            action.completed_at = None
    if body.assigned_to is not None:
        action.assigned_to = body.assigned_to
    if body.description is not None:
        action.description = body.description
    if body.due_date is not None:
        action.due_date = datetime.fromisoformat(body.due_date) if body.due_date else None
    if body.notes is not None:
        action.notes = body.notes.strip() or None

    await db.commit()

    # If just marked done, evaluate if a follow-up action is needed
    suggestion = None
    if body.status == "done" and was_not_done:
        from src.services.customer_agent import evaluate_next_action
        try:
            rec = await evaluate_next_action(action_id)
            if rec:
                due_days = rec.get("due_days", 3)
                due_date = datetime.now(timezone.utc) + __import__("datetime").timedelta(days=due_days) if due_days else None
                suggested = AgentAction(
                    organization_id=ctx.organization_id,
                    agent_message_id=rec["agent_message_id"],
                    action_type=rec["action_type"],
                    description=rec["description"],
                    due_date=due_date,
                    status="suggested",
                    created_by="DeepBlue",
                )
                db.add(suggested)
                await db.commit()
                await db.refresh(suggested)
                suggestion = {
                    **_serialize_action(suggested),
                    "reasoning": rec.get("reasoning", ""),
                }
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Next action eval failed: {e}")

    result = _serialize_action(action)
    if suggestion:
        result["suggestion"] = suggestion
    return result


@router.get("/agent-actions/{action_id}")
async def get_agent_action(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get a single action with comments."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(AgentAction.id == action_id, AgentAction.organization_id == ctx.organization_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    d = _serialize_action(action, include_comments=True)
    # Include parent message context + sibling actions for full history
    if action.agent_message_id:
        msg_result = await db.execute(select(AgentMessage).where(AgentMessage.id == action.agent_message_id, AgentMessage.organization_id == ctx.organization_id))
        msg = msg_result.scalar_one_or_none()
        if msg:
            d["from_email"] = msg.from_email
            d["customer_name"] = msg.customer_name or action.customer_name
            d["subject"] = msg.subject
            d["email_body"] = (msg.body or "")[:500]
            d["our_response"] = msg.final_response or msg.draft_response

            # Get sibling actions (other jobs from the same email) for context
            siblings_result = await db.execute(
                select(AgentAction)
                .options(selectinload(AgentAction.comments))
                .where(
                    AgentAction.agent_message_id == action.agent_message_id,
                    AgentAction.organization_id == ctx.organization_id,
                    AgentAction.id != action.id,
                )
                .order_by(AgentAction.created_at)
            )
            d["related_jobs"] = [
                {
                    "id": s.id,
                    "action_type": s.action_type,
                    "description": s.description,
                    "status": s.status,
                    "comments": [{"author": c.author, "text": c.text} for c in (s.comments or [])],
                }
                for s in siblings_result.scalars().all()
            ]
    else:
        d["customer_name"] = action.customer_name
    return d


class AddCommentBody(BaseModel):
    text: str


@router.post("/agent-actions/{action_id}/comments")
async def add_action_comment(
    action_id: str,
    body: AddCommentBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to an action item."""
    result = await db.execute(select(AgentAction).where(AgentAction.id == action_id, AgentAction.organization_id == ctx.organization_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    comment = AgentActionComment(
        organization_id=ctx.organization_id,
        action_id=action_id,
        author=f"{ctx.user.first_name} {ctx.user.last_name}",
        text=body.text.strip(),
    )
    db.add(comment)

    # Notify assignee if someone else commented
    if action.assigned_to:
        from src.models.notification import Notification
        from src.models.organization_user import OrganizationUser
        from src.models.user import User

        # Find user by first name match against assigned_to
        ou_result = await db.execute(
            select(OrganizationUser)
            .join(User, OrganizationUser.user_id == User.id)
            .where(
                OrganizationUser.organization_id == ctx.organization_id,
                User.first_name == action.assigned_to,
                User.id != ctx.user.id,  # Don't notify yourself
            )
        )
        assignee_ou = ou_result.scalar_one_or_none()
        if assignee_ou:
            db.add(Notification(
                organization_id=ctx.organization_id,
                user_id=assignee_ou.user_id,
                type="action_comment",
                title=f"Comment on: {action.description[:60]}",
                body=f"{ctx.user.first_name}: {body.text.strip()[:100]}",
                link=f"/jobs?action={action_id}",
            ))

    await db.commit()
    await db.refresh(comment)

    # Auto-answer: check if the comment asks for info we have in the database
    auto_comment = None
    if action.status in ("open", "in_progress"):
        try:
            import anthropic, os, re as re_mod, json as json_mod
            from sqlalchemy.orm import selectinload

            # Get customer/property context for this action
            customer_context = ""
            customer_id = None
            if action.agent_message_id:
                msg_check = await db.execute(select(AgentMessage).where(AgentMessage.id == action.agent_message_id, AgentMessage.organization_id == ctx.organization_id))
                parent_msg = msg_check.scalar_one_or_none()
                if parent_msg and parent_msg.matched_customer_id:
                    customer_id = parent_msg.matched_customer_id

            if customer_id:
                from src.models.customer import Customer as Cust
                from src.models.property import Property as Prop
                from src.models.water_feature import WaterFeature as WF

                cust = (await db.execute(select(Cust).where(Cust.id == customer_id))).scalar_one_or_none()
                if cust:
                    customer_context += f"\nCustomer: {cust.display_name}"
                    if cust.email: customer_context += f"\nEmail: {cust.email}"
                    if cust.phone: customer_context += f"\nPhone: {cust.phone}"
                    if cust.preferred_day: customer_context += f"\nService days: {cust.preferred_day}"
                    if cust.monthly_rate: customer_context += f"\nRate: ${cust.monthly_rate:.2f}/mo"

                    props = (await db.execute(select(Prop).where(Prop.customer_id == customer_id, Prop.is_active == True))).scalars().all()
                    for p in props:
                        customer_context += f"\nProperty: {p.full_address}"
                        if p.gate_code: customer_context += f" (Gate: {p.gate_code})"
                        if p.access_instructions: customer_context += f" Access: {p.access_instructions}"
                        if p.dog_on_property: customer_context += " DOG"
                        wfs = (await db.execute(select(WF).where(WF.property_id == p.id, WF.is_active == True))).scalars().all()
                        for wf in wfs:
                            parts = [wf.name or wf.water_type]
                            if wf.pool_gallons: parts.append(f"{wf.pool_gallons:,} gal")
                            if wf.filter_type: parts.append(f"filter: {wf.filter_type}")
                            if wf.pump_type: parts.append(f"pump: {wf.pump_type}")
                            if wf.sanitizer_type: parts.append(f"sanitizer: {wf.sanitizer_type}")
                            customer_context += f"\n  {', '.join(parts)}"

            if customer_context:
                # Ask Claude if the comment asks for info we have
                info_prompt = f"""A team member commented on a job. Does their comment ask for information that's available in our database?

Job: {action.description}
Comment: {body.text.strip()}

Customer data on file:{customer_context}

If the comment asks for info we already have (address, phone, gate code, service day, equipment, etc.), respond with JSON:
{{"has_answer": true, "answer": "the relevant info from the database, formatted naturally"}}

If the comment doesn't ask for info, or we don't have what they need:
{{"has_answer": false}}

Only answer with data that directly addresses what was asked. Don't volunteer unrelated info."""

                ai_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
                info_response = ai_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{"role": "user", "content": info_prompt}],
                )
                info_match = re_mod.search(r"\{.*\}", info_response.content[0].text, re_mod.DOTALL)
                if info_match:
                    info_data = json_mod.loads(info_match.group())
                    if info_data.get("has_answer") and info_data.get("answer"):
                        # Post an auto-comment with the info
                        auto_reply = AgentActionComment(
                            organization_id=ctx.organization_id,
                            action_id=action_id,
                            author="DeepBlue",
                            text=info_data["answer"],
                        )
                        db.add(auto_reply)
                        await db.commit()
                        await db.refresh(auto_reply)
                        auto_comment = {"author": "DeepBlue", "text": info_data["answer"]}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Auto-answer failed: {e}")

    # Evaluate if the comment resolves the action
    resolved = False
    if action.status in ("open", "in_progress"):
        try:
            import anthropic, os, re as re_mod, json as json_mod
            from sqlalchemy.orm import selectinload

            # Reload action with all comments
            action_result = await db.execute(
                select(AgentAction).options(selectinload(AgentAction.comments)).where(AgentAction.id == action_id, AgentAction.organization_id == ctx.organization_id)
            )
            action_full = action_result.scalar_one()

            comments_text = "\n".join(f"- {c.author}: {c.text}" for c in action_full.comments)

            eval_prompt = f"""An action item for a pool service company just received a new comment. Does this comment resolve/answer the action?

Action: [{action_full.action_type}] {action_full.description}
Assigned to: {action_full.assigned_to or 'unassigned'}

Comments:
{comments_text}

Latest comment by {ctx.user.first_name}: {body.text.strip()}

Respond with JSON:
{{
  "resolved": true/false,
  "update_description": "new description if the comment changes the scope of the action, or null if no change",
  "update_type": "new action_type if changed, or null",
  "reason": "brief explanation"
}}

Rules:
- "resolved" = true if the comment provides the answer, completes the task, or makes it clear no further work is needed
- Examples: someone provides the requested info, confirms work is done, answers the question
- If the comment is just a status update or partial info that doesn't fully resolve it, return resolved: false
- If the comment changes the scope (e.g., "skip inspection, just replace" or "already done, just need to invoice"), update the description to reflect the new scope
- update_description: set ONLY if the comment changes what needs to be done. Keep it concise.
- update_type: set ONLY if the action type should change (e.g., site_visit → equipment)"""

            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": eval_prompt}],
            )
            json_match = re_mod.search(r"\{.*\}", response.content[0].text, re_mod.DOTALL)
            if json_match:
                result_data = json_mod.loads(json_match.group())

                updated_desc = None
                # Update description if scope changed
                if result_data.get("update_description"):
                    action.description = result_data["update_description"]
                    updated_desc = action.description
                if result_data.get("update_type"):
                    action.action_type = result_data["update_type"]

                if result_data.get("resolved"):
                    from datetime import datetime, timezone
                    action.status = "done"
                    action.completed_at = datetime.now(timezone.utc)
                    resolved = True

                await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Comment resolution eval failed: {e}")

    return {
        "id": comment.id,
        "author": comment.author,
        "text": comment.text,
        "created_at": comment.created_at.isoformat(),
        "action_resolved": resolved,
        "action_updated": updated_desc is not None,
        "new_description": updated_desc,
        "auto_comment": auto_comment,
    }


@router.post("/agent-messages/{message_id}/draft-followup")
async def draft_followup(
    message_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Draft a follow-up email using full thread context including action comments."""
    import anthropic
    import os
    from sqlalchemy.orm import selectinload

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Get all actions + comments for this message
    actions_result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(AgentAction.agent_message_id == message_id, AgentAction.organization_id == ctx.organization_id)
    )
    all_actions = actions_result.scalars().all()

    actions_context = ""
    for a in all_actions:
        actions_context += f"\n- [{a.status}] {a.action_type}: {a.description}"
        if a.comments:
            for c in a.comments:
                actions_context += f"\n  Comment ({c.author}): {c.text}"

    # Get customer context
    customer_info = ""
    if msg.matched_customer_id:
        from src.models.customer import Customer
        cust = (await db.execute(select(Customer).where(Customer.id == msg.matched_customer_id))).scalar_one_or_none()
        if cust:
            customer_info = f"\nCustomer: {cust.display_name}"
            if cust.company_name:
                customer_info += f" ({cust.company_name})"

    prompt = f"""Draft a follow-up email for a pool service company. Use the full context below.

Original email from {msg.from_email}:
Subject: {msg.subject}
{msg.body[:1000] if msg.body else ''}
{customer_info}

Our previous reply:
{msg.final_response or msg.draft_response or 'No reply sent yet'}

Action items and team comments:{actions_context or ' None'}

Based on the action items and comments, draft a follow-up email to the client. This should continue the conversation naturally — reference what's been done, what was found, and any next steps.

Rules:
- Professional, friendly tone
- Never admit fault or accept blame
- Reference specific findings from the comments
- Keep it concise — 2-4 sentences
- End with the signature:

Best,
The {os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")} Team
{os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")}

Return ONLY the email body text, no JSON, no subject line."""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = response.content[0].text.strip()
        return {"draft": draft, "to": msg.from_email, "subject": msg.subject}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to draft: {str(e)}")


@router.post("/agent-messages/{message_id}/send-followup")
async def send_followup(
    message_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up email."""
    from datetime import datetime, timezone
    from src.services.customer_agent import send_email_response

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    response_text = body.response_text
    if not response_text:
        raise HTTPException(status_code=400, detail="No response text provided")

    success = await send_email_response(msg.from_email, msg.subject or "", response_text)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    # Log as a note on the message
    msg.notes = (msg.notes or "") + f"\nFollow-up sent by {ctx.user.first_name} {ctx.user.last_name} at {datetime.now(timezone.utc).isoformat()}"
    msg.notes = msg.notes.strip()
    await db.commit()

    # Evaluate if open actions should be closed based on the follow-up content
    import anthropic, os, json as json_mod
    from sqlalchemy.orm import selectinload

    actions_result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(
            AgentAction.agent_message_id == message_id,
            AgentAction.organization_id == ctx.organization_id,
            AgentAction.status.in_(("open", "in_progress")),
        )
    )
    open_actions = actions_result.scalars().all()

    closed_actions = []
    ask_actions = []

    if open_actions:
        actions_list = []
        for a in open_actions:
            comments_text = ""
            if a.comments:
                comments_text = " | Comments: " + "; ".join(c.text for c in a.comments)
            actions_list.append(f"- ID:{a.id[:8]} [{a.action_type}] {a.description}{comments_text}")

        eval_prompt = f"""A follow-up email was just sent to a client. Based on its content, determine which open action items (if any) are now complete.

Follow-up email sent:
{response_text}

Open action items:
{chr(10).join(actions_list)}

For each action, respond with JSON array:
[
  {{"id": "first8chars", "status": "done|open|ask", "reason": "why"}}
]

Rules:
- "done" = the follow-up clearly addresses/completes this action
- "open" = the follow-up doesn't address this action, it's still needed
- "ask" = unclear whether this is resolved, need user confirmation
- Be conservative — only mark done if the email clearly covers it"""

        try:
            ai_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            eval_response = ai_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": eval_prompt}],
            )
            eval_text = eval_response.content[0].text
            import re
            json_match = re.search(r"\[.*\]", eval_text, re.DOTALL)
            if json_match:
                evaluations = json_mod.loads(json_match.group())
                for ev in evaluations:
                    action_prefix = ev.get("id", "")
                    status = ev.get("status", "open")
                    reason = ev.get("reason", "")
                    for a in open_actions:
                        if a.id.startswith(action_prefix):
                            if status == "done":
                                a.status = "done"
                                a.completed_at = datetime.now(timezone.utc)
                                closed_actions.append({"id": a.id, "description": a.description, "reason": reason})
                            elif status == "ask":
                                ask_actions.append({"id": a.id, "description": a.description, "reason": reason})
                await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Action evaluation after follow-up failed: {e}")

    return {
        "sent": True,
        "to": msg.from_email,
        "closed_actions": closed_actions,
        "ask_actions": ask_actions,
    }


@router.post("/agent-actions/{action_id}/draft-invoice")
async def draft_invoice_from_action(
    action_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """AI drafts invoice line items from action context (comments, description, customer)."""
    import anthropic, os, json as json_mod, re
    from sqlalchemy.orm import selectinload

    # Load action with comments + parent message
    result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(AgentAction.id == action_id, AgentAction.organization_id == ctx.organization_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    msg_result = await db.execute(select(AgentMessage).where(AgentMessage.id == action.agent_message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = msg_result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Parent message not found")

    # Get customer ID
    customer_id = msg.matched_customer_id
    customer_name = msg.customer_name or msg.from_email

    # Build context
    comments_text = ""
    if action.comments:
        comments_text = "\n".join(f"- {c.author}: {c.text}" for c in action.comments)

    # Get all sibling actions for full picture
    siblings = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(AgentAction.agent_message_id == msg.id, AgentAction.organization_id == ctx.organization_id)
    )
    all_actions_text = ""
    for a in siblings.scalars().all():
        all_actions_text += f"\n- [{a.status}] {a.action_type}: {a.description}"
        if a.comments:
            for c in a.comments:
                all_actions_text += f"\n  {c.author}: {c.text}"

    prompt = f"""Generate invoice line items for a pool service company based on this context.

Customer: {customer_name}
Original email subject: {msg.subject}

Action item: {action.action_type} — {action.description}

All action items and comments for this event:{all_actions_text}

Based on the work described, generate invoice line items. Extract specific services, parts, and costs from the comments and descriptions.

Respond with JSON:
{{
  "subject": "Brief invoice subject (e.g., 'Pool Valve Repair - Pinebrook Village')",
  "line_items": [
    {{
      "description": "what was done or provided",
      "quantity": 1,
      "unit_price": 0.00
    }}
  ],
  "notes": "any notes for the invoice"
}}

Rules:
- Extract actual dollar amounts mentioned in comments if available
- If no price was mentioned, use unit_price: 0 and note "Price TBD" in description
- Separate labor from parts/materials if both mentioned
- Keep descriptions clear and professional
- Include a subject line suitable for the invoice header"""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
        if json_match:
            draft = json_mod.loads(json_match.group())
            return {
                "customer_id": customer_id,
                "customer_name": customer_name,
                "subject": draft.get("subject", f"Service - {customer_name}"),
                "line_items": draft.get("line_items", []),
                "notes": draft.get("notes", ""),
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to draft invoice: {str(e)}")

    return {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "subject": f"Service - {customer_name}",
        "line_items": [],
        "notes": "",
    }


@router.post("/agent-messages/{message_id}/revise-draft")
async def revise_draft(
    message_id: str,
    body: ReviseDraftBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Revise a draft based on user instruction."""
    import anthropic
    import os

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id, AgentMessage.organization_id == ctx.organization_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    prompt = f"""Revise this email draft based on the instruction below.

Original email from {msg.from_email}:
Subject: {msg.subject}

Current draft:
{body.draft}

Instruction: {body.instruction}

Rules:
- Apply the instruction to the draft
- Keep the same general structure and signature
- Never admit fault or accept blame
- Return ONLY the revised email text, nothing else"""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"draft": response.content[0].text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revise: {str(e)}")


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
