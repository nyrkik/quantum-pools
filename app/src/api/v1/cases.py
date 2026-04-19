"""ServiceCase endpoints — org-scoped."""

import json
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.models.service_case import ServiceCase
from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.invoice import Invoice
from src.models.internal_message import InternalThread, InternalMessage
from src.services.service_case_service import ServiceCaseService
from src.presenters.case_presenter import CasePresenter

router = APIRouter(prefix="/cases", tags=["cases"])


class CreateCaseBody(BaseModel):
    title: str
    customer_id: Optional[str] = None
    billing_name: Optional[str] = None
    priority: str = "normal"


@router.post("", status_code=201)
async def create_case(
    body: CreateCaseBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new case."""
    from src.services.events.actor_factory import actor_from_org_ctx
    svc = ServiceCaseService(db)
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    case = await svc.create(
        org_id=ctx.organization_id,
        title=body.title,
        source="manual",
        customer_id=body.customer_id,
        billing_name=body.billing_name,
        priority=body.priority,
        created_by=user_name,
        manager_user_id=ctx.user.id,
        actor=actor_from_org_ctx(ctx),
    )
    await db.commit()
    return {"id": case.id, "case_number": case.case_number, "title": case.title}


@router.get("")
async def list_cases(
    status: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ServiceCaseService(db)
    result = await svc.list_cases(
        org_id=ctx.organization_id,
        status=status,
        customer_id=customer_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    presenter = CasePresenter(db)
    items = await presenter.many(result["items"])
    return {"items": items, "total": result["total"]}


@router.get("/{case_id}")
async def get_case(
    case_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    presenter = CasePresenter(db)
    d = await presenter.one(case)

    from src.models.agent_action_task import AgentActionTask
    from src.models.invoice import InvoiceLineItem

    # Load jobs with comments and tasks
    jobs_result = await db.execute(
        select(AgentAction)
        .options(selectinload(AgentAction.comments), selectinload(AgentAction.tasks))
        .where(AgentAction.case_id == case_id)
        .order_by(AgentAction.created_at)
    )
    jobs = jobs_result.scalars().all()
    d["jobs"] = [
        {
            "id": j.id,
            "description": j.description,
            "action_type": j.action_type,
            "status": j.status,
            "assigned_to": j.assigned_to,
            "due_date": presenter._iso(j.due_date),
            "completed_at": presenter._iso(j.completed_at),
            "created_at": presenter._iso(j.created_at),
            "notes": j.notes,
            "closed_by_case_cascade": j.closed_by_case_cascade,
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status, "assigned_to": t.assigned_to, "sort_order": t.sort_order}
                for t in (j.tasks or [])
            ],
            "comments": [
                {"id": c.id, "author": c.author, "text": c.text, "created_at": presenter._iso(c.created_at)}
                for c in (j.comments or [])
                if not c.text.startswith("[DRAFT_EMAIL]") and not c.text.startswith("[SENT_EMAIL]")
            ],
        }
        for j in jobs
    ]

    # Load threads with full messages
    threads_result = await db.execute(
        select(AgentThread)
        .options(selectinload(AgentThread.messages))
        .where(AgentThread.case_id == case_id)
        .order_by(AgentThread.created_at)
    )
    threads = threads_result.scalars().all()
    d["threads"] = [
        {
            "id": t.id,
            "subject": t.subject,
            "contact_email": t.contact_email,
            "status": t.status,
            "message_count": t.message_count,
            "messages": [
                {
                    "id": m.id,
                    "direction": m.direction,
                    "from_email": m.from_email,
                    "to_email": m.to_email,
                    "subject": m.subject,
                    "body": m.body,
                    "status": m.status,
                    "received_at": presenter._iso(m.received_at),
                    "sent_at": presenter._iso(m.sent_at),
                }
                for m in sorted(t.messages or [], key=lambda x: x.received_at or x.created_at)
            ],
        }
        for t in threads
    ]

    # Load invoices with line items
    invoices_result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.case_id == case_id)
        .order_by(Invoice.created_at)
    )
    d["invoices"] = [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "document_type": inv.document_type,
            "subject": inv.subject,
            "status": inv.status,
            "total": float(inv.total or 0),
            "balance": float(inv.balance or 0),
            "created_at": presenter._iso(inv.created_at),
            # `approved_at` gates the "convert estimate to invoice" affordance
            # in the UI — backend rejects conversion when this is null.
            "approved_at": presenter._iso(inv.approved_at),
            "line_items": [
                {"description": li.description, "quantity": float(li.quantity), "unit_price": float(li.unit_price), "amount": float(li.amount or 0)}
                for li in sorted(inv.line_items or [], key=lambda x: x.sort_order)
            ],
        }
        for inv in invoices_result.scalars().all()
    ]

    # Load DeepBlue conversations
    from src.models.deepblue_conversation import DeepBlueConversation
    db_convos = (await db.execute(
        select(DeepBlueConversation)
        .where(DeepBlueConversation.case_id == case_id)
        .order_by(DeepBlueConversation.updated_at.desc())
    )).scalars().all()
    d["deepblue_conversations"] = [
        {
            "id": c.id,
            "title": c.title,
            "user_id": c.user_id,
            "message_count": len(json.loads(c.messages_json or "[]")),
            "messages": json.loads(c.messages_json or "[]"),
            "created_at": presenter._iso(c.created_at),
            "updated_at": presenter._iso(c.updated_at),
        }
        for c in db_convos
    ]

    # Load internal messages
    internal_result = await db.execute(
        select(InternalThread)
        .options(selectinload(InternalThread.messages))
        .where(InternalThread.case_id == case_id)
        .order_by(InternalThread.created_at)
    )
    internal_threads = internal_result.scalars().all()
    d["internal_threads"] = [
        {
            "id": it.id,
            "subject": it.subject,
            "message_count": it.message_count,
            "messages": [
                {
                    "id": m.id,
                    "from_user_id": m.from_user_id,
                    "text": m.text,
                    "created_at": presenter._iso(m.created_at),
                }
                for m in sorted(it.messages or [], key=lambda x: x.created_at)
            ],
        }
        for it in internal_threads
    ]

    # Build unified timeline from emails + job comments + internal messages
    timeline = []

    for t in d["threads"]:
        for m in t["messages"]:
            timeline.append({
                "id": m["id"],
                "type": "email",
                "timestamp": m["received_at"] or m["sent_at"],
                "title": f"{'Sent' if m['direction'] == 'outbound' else 'Received'}: {m['subject'] or '(no subject)'}",
                "body": m["body"],
                "actor": m["from_email"],
                "metadata": {"direction": m["direction"], "status": m["status"], "thread_id": t["id"]},
            })

    JOB_TYPES = {"repair", "site_visit", "bid", "equipment"}
    from datetime import date as date_type
    today = date_type.today().isoformat()
    for j in d["jobs"]:
        label = "Job" if j["action_type"] in JOB_TYPES else "Task"
        is_cancelled = j["status"] == "cancelled"
        created_today = j["created_at"] and j["created_at"][:10] == today

        # Created today + cancelled = remove entirely (mistake, no audit value)
        if is_cancelled and created_today:
            continue

        title_prefix = f"{label} cancelled" if is_cancelled else f"{label} created"
        timeline.append({
            "id": f"job-created-{j['id']}",
            "type": "job_event",
            "timestamp": j["created_at"],
            "title": f"{title_prefix}: {j['description'][:80]}",
            "body": None,
            "actor": j.get("assigned_to"),
            "metadata": {"action_id": j["id"], "event": "cancelled" if is_cancelled else "created", "action_type": j["action_type"], "status": j["status"]},
        })
        if j.get("completed_at") and not is_cancelled:
            timeline.append({
                "id": f"job-done-{j['id']}",
                "type": "job_event",
                "timestamp": j["completed_at"],
                "title": f"{label} completed: {j['description'][:80]}",
                "body": None,
                "actor": j.get("assigned_to"),
                "metadata": {"action_id": j["id"], "event": "completed"},
            })
        # Job comments
        for c in j["comments"]:
            timeline.append({
                "id": c["id"],
                "type": "comment",
                "timestamp": c["created_at"],
                "title": f"{c['author']}",
                "body": c["text"],
                "actor": c["author"],
                "metadata": {"action_id": j["id"], "job_description": j["description"]},
            })

    for inv in d["invoices"]:
        timeline.append({
            "id": inv["id"],
            "type": "invoice_event",
            "timestamp": inv["created_at"],
            "title": f"{inv['document_type'].replace('_', ' ').title()} {inv['invoice_number'] or 'Draft'} — ${inv['total']:,.2f}",
            "body": inv["subject"],
            "actor": None,
            "metadata": {"invoice_id": inv["id"], "document_type": inv["document_type"], "status": inv["status"]},
        })

    # Internal team messages
    for it in d.get("internal_threads", []):
        for m in it["messages"]:
            timeline.append({
                "id": m["id"],
                "type": "internal_message",
                "timestamp": m["created_at"],
                "title": f"Team message" + (f" — {it['subject']}" if it.get("subject") else ""),
                "body": m["text"],
                "actor": m.get("from_user_id"),
                "metadata": {"internal_thread_id": it["id"]},
            })

    timeline.sort(key=lambda x: x["timestamp"] or "")
    d["timeline"] = timeline

    return d


@router.put("/{case_id}")
async def update_case(
    case_id: str,
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if "title" in body:
        case.title = body["title"][:300]
    status_override = "status" in body
    prior_manager_user_id = case.manager_user_id
    prior_manager_name = case.manager_name
    closed_this_request = False
    reopened_this_request = False
    cascade_jobs_closed = 0
    cascade_jobs_reopened = 0  # reserved; manual reopen doesn't cascade here (explicit API lives in /reopen-jobs)
    if status_override:
        prior_status = case.status
        case.status = body["status"]
        if body["status"] == "closed":
            from datetime import datetime, timezone
            case.closed_at = datetime.now(timezone.utc)
            closed_this_request = prior_status not in ("closed", "cancelled")
        elif body["status"] not in ("closed", "cancelled"):
            # Reopening: clear closed_at.
            case.closed_at = None
            reopened_this_request = prior_status in ("closed", "cancelled")
        # When transitioning to a terminal state, mirror it onto any open jobs.
        # Closing a case with open work underneath would leave orphaned actionable items.
        if body["status"] in ("closed", "cancelled") and prior_status not in ("closed", "cancelled"):
            cascade_jobs_closed = await svc.close_open_jobs(
                case_id, new_status="done" if body["status"] == "closed" else "cancelled",
            )
    if "priority" in body:
        case.priority = body["priority"]
    if "assigned_to_name" in body:
        case.assigned_to_name = body["assigned_to_name"]
    manager_changed = False
    if "manager_name" in body or "manager_user_id" in body:
        new_manager_user_id = body.get("manager_user_id")
        new_manager_name = body.get("manager_name")
        manager_changed = (
            new_manager_user_id != prior_manager_user_id
            or new_manager_name != prior_manager_name
        )
        case.manager_user_id = new_manager_user_id
        case.manager_name = new_manager_name
        case.assigned_to_name = body.get("assigned_to_name", new_manager_name)
        case.assigned_to_user_id = body.get("assigned_to_user_id", new_manager_user_id)

    await db.flush()
    # Skip child-state re-derivation if the user explicitly set status in this
    # request — manual override wins. Otherwise the user's "close this case"
    # action gets immediately overwritten by the auto-derived pending_payment /
    # in_progress etc. based on open invoices, done jobs, and so on.
    if not status_override:
        await svc.update_status_from_children(case_id)

    from src.services.events.platform_event_service import PlatformEventService
    from src.services.events.actor_factory import actor_from_org_ctx
    actor = actor_from_org_ctx(ctx)
    refs = {"case_id": case_id}
    if case.customer_id:
        refs["customer_id"] = case.customer_id
    if closed_this_request:
        await PlatformEventService.emit(
            db=db, event_type="case.closed", level="user_action", actor=actor,
            organization_id=ctx.organization_id, entity_refs=refs,
            payload={
                "reason": "manual",
                "auto_closed": False,
                "cascade_jobs_closed": cascade_jobs_closed,
            },
        )
    if reopened_this_request:
        await PlatformEventService.emit(
            db=db, event_type="case.reopened", level="user_action", actor=actor,
            organization_id=ctx.organization_id, entity_refs=refs,
            payload={"cascade_jobs_reopened": cascade_jobs_reopened},
        )
    if manager_changed:
        mgr_refs = dict(refs)
        if case.manager_user_id:
            mgr_refs["user_id"] = case.manager_user_id
        await PlatformEventService.emit(
            db=db, event_type="case.manager_changed", level="user_action", actor=actor,
            organization_id=ctx.organization_id, entity_refs=mgr_refs,
            payload={
                "prior_manager_user_id": prior_manager_user_id,
                "prior_manager_name": prior_manager_name,
                "new_manager_user_id": case.manager_user_id,
                "new_manager_name": case.manager_name,
            },
        )

    await db.commit()
    presenter = CasePresenter(db)
    return await presenter.one(case)


@router.post("/{case_id}/reopen-jobs")
async def reopen_cascade_jobs(
    case_id: str,
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Reopen jobs that were cascade-closed when the case was closed.

    Body: {"job_ids": ["...", ...]}

    Only jobs flagged `closed_by_case_cascade` on this case can be reopened through here.
    Human-closed jobs are immutable via this path to protect the audit trail.
    """
    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    job_ids = body.get("job_ids") or []
    if not isinstance(job_ids, list):
        raise HTTPException(status_code=400, detail="job_ids must be a list")
    count = await svc.reopen_cascade_jobs(case_id, [str(j) for j in job_ids])
    if count:
        await svc.update_status_from_children(case_id)

    # Emit case.reopened when the case came back from terminal state —
    # update_status_from_children may have flipped status from closed.
    from src.services.events.platform_event_service import PlatformEventService
    from src.services.events.actor_factory import actor_from_org_ctx
    refs = {"case_id": case_id}
    if case.customer_id:
        refs["customer_id"] = case.customer_id
    await db.refresh(case)
    if count and case.status not in ("closed", "cancelled"):
        await PlatformEventService.emit(
            db=db, event_type="case.reopened",
            level="user_action",
            actor=actor_from_org_ctx(ctx),
            organization_id=ctx.organization_id,
            entity_refs=refs,
            payload={"cascade_jobs_reopened": count},
        )

    await db.commit()
    from src.core.events import EventType, publish
    try:
        await publish(EventType.CASE_UPDATED, ctx.organization_id, {"case_id": case_id, "action": "jobs_reopened", "count": count})
    except Exception:
        pass
    return {"reopened": count}


@router.post("/{case_id}/link")
async def link_entity(
    case_id: str,
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually link an entity to a case.

    Supported types: job, thread, invoice, internal_thread, deepblue_conversation.
    Cross-org mutations are blocked by ServiceCaseService.set_entity_case.
    """
    entity_type = body.get("type")
    entity_id = body.get("id")
    if not entity_type or not entity_id:
        raise HTTPException(status_code=400, detail="type and id required")

    svc = ServiceCaseService(db)
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip() or None
    try:
        result = await svc.set_entity_case(
            org_id=ctx.organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            new_case_id=case_id,
            user_name=user_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"linked": True, **result}


@router.delete("/{case_id}/link")
async def unlink_entity(
    case_id: str,
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink an entity from a case.

    Only unlinks if the entity's current case_id matches `case_id` — a missed
    org/case guard cannot silently wipe another case's links. Cross-org is
    enforced by ServiceCaseService.set_entity_case.
    """
    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip() or None
    try:
        # Verify the entity is currently attached to THIS case. Prevents a
        # valid-but-unrelated unlink request from clearing a link that belongs
        # to a different case (cheap guard, zero downside).
        from src.services.service_case_service import LINKABLE_MODELS
        model = LINKABLE_MODELS.get(entity_type)
        if not model:
            raise HTTPException(status_code=400, detail=f"unknown type: {entity_type}")
        current = (await db.execute(
            select(model.case_id).where(
                model.id == entity_id,
                model.organization_id == ctx.organization_id,
            )
        )).scalar_one_or_none()
        if current != case_id:
            # Already unlinked or attached elsewhere — idempotent success.
            return {"unlinked": True, "changed": False}

        result = await svc.set_entity_case(
            org_id=ctx.organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            new_case_id=None,
            user_name=user_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"unlinked": True, **result}


class CreateJobInCaseBody(BaseModel):
    action_type: str = "follow_up"
    description: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/{case_id}/jobs")
async def create_job_in_case(
    case_id: str,
    body: CreateJobInCaseBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a job within a case."""
    import uuid
    from datetime import datetime, timezone

    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    due = None
    if body.due_date:
        due = datetime.fromisoformat(body.due_date)

    from src.services.agent_action_service import AgentActionService
    from src.services.events.actor_factory import actor_from_org_ctx
    action = await AgentActionService(db).add_job(
        org_id=ctx.organization_id,
        action_type=body.action_type,
        description=body.description,
        source="manual",
        actor=actor_from_org_ctx(ctx),
        case_id=case_id,
        customer_id=case.customer_id,
        assigned_to=body.assigned_to,
        due_date=due,
        notes=body.notes,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip(),
    )
    await svc.update_counts(case_id)
    await db.commit()

    return {
        "id": action.id,
        "description": action.description,
        "action_type": action.action_type,
        "status": action.status,
    }
