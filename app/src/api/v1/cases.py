"""ServiceCase endpoints — org-scoped."""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
            "line_items": [
                {"description": li.description, "quantity": float(li.quantity), "unit_price": float(li.unit_price), "amount": float(li.amount or 0)}
                for li in sorted(inv.line_items or [], key=lambda x: x.sort_order)
            ],
        }
        for inv in invoices_result.scalars().all()
    ]

    # Build unified timeline from emails + job comments
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

    for j in d["jobs"]:
        # Job created
        timeline.append({
            "id": f"job-created-{j['id']}",
            "type": "job_event",
            "timestamp": j["created_at"],
            "title": f"Job created: {j['description'][:80]}",
            "body": None,
            "actor": j.get("assigned_to"),
            "metadata": {"action_id": j["id"], "event": "created", "action_type": j["action_type"], "status": j["status"]},
        })
        # Job completed
        if j.get("completed_at"):
            timeline.append({
                "id": f"job-done-{j['id']}",
                "type": "job_event",
                "timestamp": j["completed_at"],
                "title": f"Job completed: {j['description'][:80]}",
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
    if "status" in body:
        case.status = body["status"]
    if "priority" in body:
        case.priority = body["priority"]
    if "assigned_to_name" in body:
        case.assigned_to_name = body["assigned_to_name"]

    await db.commit()
    presenter = CasePresenter(db)
    return await presenter.one(case)


@router.post("/{case_id}/link")
async def link_entity(
    case_id: str,
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually link a job, thread, or invoice to a case."""
    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    entity_type = body.get("type")  # "job", "thread", "invoice"
    entity_id = body.get("id")
    if not entity_type or not entity_id:
        raise HTTPException(status_code=400, detail="type and id required")

    if entity_type == "job":
        action = (await db.execute(select(AgentAction).where(AgentAction.id == entity_id, AgentAction.organization_id == ctx.organization_id))).scalar_one_or_none()
        if not action:
            raise HTTPException(status_code=404, detail="Job not found")
        action.case_id = case_id
    elif entity_type == "thread":
        thread = (await db.execute(select(AgentThread).where(AgentThread.id == entity_id, AgentThread.organization_id == ctx.organization_id))).scalar_one_or_none()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        thread.case_id = case_id
    elif entity_type == "invoice":
        invoice = (await db.execute(select(Invoice).where(Invoice.id == entity_id, Invoice.organization_id == ctx.organization_id))).scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        invoice.case_id = case_id
    else:
        raise HTTPException(status_code=400, detail="type must be job, thread, or invoice")

    await svc.update_counts(case_id)
    await db.commit()
    return {"linked": True}


@router.delete("/{case_id}/link")
async def unlink_entity(
    case_id: str,
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink a job, thread, or invoice from a case."""
    svc = ServiceCaseService(db)
    case = await svc.get(ctx.organization_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if entity_type == "job":
        action = (await db.execute(select(AgentAction).where(AgentAction.id == entity_id))).scalar_one_or_none()
        if action:
            action.case_id = None
    elif entity_type == "thread":
        thread = (await db.execute(select(AgentThread).where(AgentThread.id == entity_id))).scalar_one_or_none()
        if thread:
            thread.case_id = None
    elif entity_type == "invoice":
        invoice = (await db.execute(select(Invoice).where(Invoice.id == entity_id))).scalar_one_or_none()
        if invoice:
            invoice.case_id = None

    await svc.update_counts(case_id)
    await db.commit()
    return {"unlinked": True}


class CreateJobInCaseBody(BaseModel):
    action_type: str = "follow_up"
    description: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


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

    action = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        case_id=case_id,
        customer_id=case.customer_id,
        action_type=body.action_type,
        description=body.description,
        assigned_to=body.assigned_to,
        due_date=due,
        status="open",
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip(),
    )
    db.add(action)
    await svc.update_counts(case_id)
    await db.commit()

    return {
        "id": action.id,
        "description": action.description,
        "action_type": action.action_type,
        "status": action.status,
    }
