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
    search: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List agent messages with pagination."""
    base = select(AgentMessage)
    if status:
        base = base.where(AgentMessage.status == status)
    if category:
        base = base.where(AgentMessage.category == category)
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

    total = (await db.execute(select(func.count(AgentMessage.id)))).scalar() or 0

    status_counts = {}
    for s in ("pending", "sent", "auto_sent", "rejected", "ignored"):
        c = (await db.execute(
            select(func.count(AgentMessage.id)).where(AgentMessage.status == s)
        )).scalar() or 0
        status_counts[s] = c

    cat_result = await db.execute(
        select(AgentMessage.category, func.count(AgentMessage.id))
        .where(AgentMessage.category.isnot(None))
        .group_by(AgentMessage.category)
    )
    by_category = {row[0]: row[1] for row in cat_result.all()}

    urg_result = await db.execute(
        select(AgentMessage.urgency, func.count(AgentMessage.id))
        .where(AgentMessage.urgency.isnot(None))
        .group_by(AgentMessage.urgency)
    )
    by_urgency = {row[0]: row[1] for row in urg_result.all()}

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = (await db.execute(
        select(func.count(AgentMessage.id)).where(AgentMessage.received_at >= since_24h)
    )).scalar() or 0

    # Action item counts
    open_actions = (await db.execute(
        select(func.count(AgentAction.id)).where(AgentAction.status.in_(("open", "in_progress")))
    )).scalar() or 0
    overdue_actions = (await db.execute(
        select(func.count(AgentAction.id)).where(
            AgentAction.status.in_(("open", "in_progress")),
            AgentAction.due_date < datetime.now(timezone.utc),
        )
    )).scalar() or 0

    # Avg response time for sent messages (seconds)
    from sqlalchemy import extract
    avg_result = await db.execute(
        select(func.avg(extract("epoch", AgentMessage.sent_at) - extract("epoch", AgentMessage.received_at)))
        .where(AgentMessage.status.in_(("sent", "auto_sent")), AgentMessage.sent_at.isnot(None))
    )
    avg_response_sec = avg_result.scalar()

    # Stale pending count (> 30 min)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale_pending = (await db.execute(
        select(func.count(AgentMessage.id)).where(
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
    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    d = _serialize_agent_msg(msg, include_body=True)
    # Include actions
    actions_result = await db.execute(
        select(AgentAction).where(AgentAction.agent_message_id == message_id).order_by(AgentAction.created_at)
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

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
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

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
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
    """Dismiss a message — no reply, no learning impact. Cancels associated actions."""
    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Cannot dismiss message with status '{msg.status}'")

    msg.status = "ignored"
    msg.notes = (msg.notes or "") + "\nDismissed by " + f"{ctx.user.first_name} {ctx.user.last_name}"
    msg.notes = msg.notes.strip()

    # Cancel associated actions
    actions_result = await db.execute(
        select(AgentAction).where(
            AgentAction.agent_message_id == message_id,
            AgentAction.status.in_(("open", "in_progress")),
        )
    )
    for action in actions_result.scalars().all():
        action.status = "cancelled"

    await db.commit()
    return {"dismissed": True}


@router.delete("/agent-messages/{message_id}")
async def delete_agent_message(
    message_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message and its actions entirely — for test/spam that got through."""
    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Delete associated actions first
    actions_result = await db.execute(
        select(AgentAction).where(AgentAction.agent_message_id == message_id)
    )
    for action in actions_result.scalars().all():
        await db.delete(action)

    await db.delete(msg)
    await db.commit()
    return {"deleted": True}


# --- Agent Actions ---

@router.get("/agent-actions")
async def list_agent_actions(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List agent action items."""
    query = select(AgentAction, AgentMessage).join(
        AgentMessage, AgentAction.agent_message_id == AgentMessage.id
    ).order_by(
        # Open first, then by due date
        desc(AgentAction.status.in_(("open", "in_progress"))),
        AgentAction.due_date.asc().nulls_last(),
    ).limit(limit)
    if status:
        query = query.where(AgentAction.status == status)
    result = await db.execute(query)
    rows = result.all()
    return [
        {
            **_serialize_action(action),
            "from_email": msg.from_email,
            "customer_name": msg.customer_name,
            "subject": msg.subject,
        }
        for action, msg in rows
    ]


class CreateActionBody(BaseModel):
    agent_message_id: str
    action_type: str
    description: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


@router.post("/agent-actions")
async def create_agent_action(
    body: CreateActionBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Manually create an action item."""
    from datetime import datetime, timezone
    due = datetime.fromisoformat(body.due_date) if body.due_date else None
    action = AgentAction(
        agent_message_id=body.agent_message_id,
        action_type=body.action_type,
        description=body.description,
        assigned_to=body.assigned_to,
        due_date=due,
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
    result = await db.execute(select(AgentAction).where(AgentAction.id == action_id))
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
                    agent_message_id=rec["agent_message_id"],
                    action_type=rec["action_type"],
                    description=rec["description"],
                    due_date=due_date,
                    status="suggested",
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
        .where(AgentAction.id == action_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    d = _serialize_action(action, include_comments=True)
    # Include parent message context
    msg_result = await db.execute(select(AgentMessage).where(AgentMessage.id == action.agent_message_id))
    msg = msg_result.scalar_one_or_none()
    if msg:
        d["from_email"] = msg.from_email
        d["customer_name"] = msg.customer_name
        d["subject"] = msg.subject
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
    result = await db.execute(select(AgentAction).where(AgentAction.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    comment = AgentActionComment(
        action_id=action_id,
        author=f"{ctx.user.first_name} {ctx.user.last_name}",
        text=body.text.strip(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return {"id": comment.id, "author": comment.author, "text": comment.text, "created_at": comment.created_at.isoformat()}


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

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Get all actions + comments for this message
    actions_result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments))
        .where(AgentAction.agent_message_id == message_id)
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
The Sapphire Pools Team
contact@sapphire-pools.com

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

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
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


class ReviseDraftBody(BaseModel):
    draft: str
    instruction: str


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

    result = await db.execute(select(AgentMessage).where(AgentMessage.id == message_id))
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
