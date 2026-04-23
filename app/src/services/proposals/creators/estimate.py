"""Proposal creator: `estimate` entity_type.

Delegates to `InvoiceService.create(document_type="estimate")` — the
canonical invoice/estimate creation path.

When `thread_id` is present in the payload, the creator also handles
job-linking in the same transaction: prefers an existing repair/site_visit
job on the thread, falls back to a matched-customer open job, and
otherwise creates a new `bid` job via `AgentActionService.add_job`. This
mirrors the job-linking semantics that used to live in
`ThreadAIService.draft_estimate_from_thread` pre-Phase-5.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction
from src.models.agent_thread import AgentThread
from src.services.events.platform_event_service import Actor
from src.services.invoice_service import InvoiceService
from src.services.job_invoice_service import link_job_invoice
from src.services.proposals.registry import register


class EstimateLineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    is_taxed: bool = False
    service_id: Optional[str] = None


class EstimateProposalPayload(BaseModel):
    """Fields a proposal can commit to an estimate.

    `customer_id` is optional ONLY when `billing_name` is provided
    (one-off / non-DB customer). `line_items` must be non-empty — a
    $0 estimate has no useful meaning.

    `thread_id`, when present, triggers job-linking: the creator looks
    for an existing job on the thread (repair/site_visit preferred), or
    on the matched customer, and links the new estimate to it. If no
    job exists, a new `bid` job is created and linked.
    """

    customer_id: Optional[str] = None
    billing_name: Optional[str] = None
    subject: Optional[str] = None
    notes: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    case_id: Optional[str] = None
    thread_id: Optional[str] = None
    line_items: list[EstimateLineItem] = Field(..., min_length=1)


async def _find_or_create_linked_job(
    *,
    db: AsyncSession,
    org_id: str,
    actor: Actor,
    thread: AgentThread,
    subject: str,
) -> AgentAction:
    """Find the best existing job to link, or create a new bid job.

    Preference order:
      1. Jobs directly on this thread (repair/site_visit preferred).
      2. Jobs on the matched customer (repair/site_visit preferred).
      3. New `bid` job created for this thread + customer.
    """
    # 1. Thread-linked jobs
    thread_jobs = (await db.execute(
        select(AgentAction).where(
            AgentAction.thread_id == thread.id,
            AgentAction.organization_id == org_id,
            AgentAction.status.in_(("open", "in_progress", "pending_approval")),
        )
    )).scalars().all()
    if thread_jobs:
        preferred = [j for j in thread_jobs if j.action_type in ("repair", "site_visit")]
        return preferred[0] if preferred else thread_jobs[0]

    # 2. Customer-matched open jobs (covers manually-created jobs)
    if thread.matched_customer_id:
        cust_jobs = (await db.execute(
            select(AgentAction).where(
                AgentAction.organization_id == org_id,
                AgentAction.customer_id == thread.matched_customer_id,
                AgentAction.status.in_(("open", "in_progress", "pending_approval")),
            ).order_by(desc(AgentAction.created_at))
        )).scalars().all()
        if cust_jobs:
            preferred = [j for j in cust_jobs if j.action_type in ("repair", "site_visit")]
            return preferred[0] if preferred else cust_jobs[0]

    # 3. Create a new bid job
    from src.services.agent_action_service import AgentActionService
    return await AgentActionService(db).add_job(
        org_id=org_id,
        action_type="bid",
        description=(subject or thread.subject or "Service Estimate")[:60],
        source="proposal_accepted",
        actor=actor,
        case_id=thread.case_id,
        thread_id=thread.id,
        customer_id=thread.matched_customer_id,
        customer_name=thread.customer_name,
        job_path="customer",
    )


@register("estimate", schema=EstimateProposalPayload)
async def create_estimate_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    """Runs in ProposalService.accept's transaction."""
    from datetime import date as _date

    invoice = await InvoiceService(db).create(
        org_id=org_id,
        customer_id=payload.get("customer_id"),
        actor=actor,
        source="proposal_accepted",
        line_items_data=payload["line_items"],
        document_type="estimate",
        subject=payload.get("subject"),
        notes=payload.get("notes"),
        issue_date=payload.get("issue_date") or _date.today(),
        due_date=payload.get("due_date"),
        case_id=payload.get("case_id"),
        billing_name=payload.get("billing_name"),
    )

    thread_id = payload.get("thread_id")
    if thread_id:
        thread = (await db.execute(
            select(AgentThread).where(
                AgentThread.id == thread_id,
                AgentThread.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if thread is not None:
            job = await _find_or_create_linked_job(
                db=db, org_id=org_id, actor=actor,
                thread=thread, subject=payload.get("subject") or "",
            )
            await link_job_invoice(db, job.id, invoice.id)

    return invoice
