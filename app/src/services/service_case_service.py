"""ServiceCase service — CRUD, matching, status management, entity linking."""

import uuid
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.service_case import ServiceCase
from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_thread import AgentThread
from src.models.invoice import Invoice
from src.models.internal_message import InternalThread
from src.models.deepblue_conversation import DeepBlueConversation

logger = logging.getLogger(__name__)


# Single source of truth for the set of entity types that can be linked to a case.
# Adding a new linkable entity type requires:
#   1. Adding a case_id FK on the entity's model
#   2. Adding an entry here mapping type-name -> SQLAlchemy model class
#   3. Extending update_counts() below to maintain a denormalized count
LINKABLE_MODELS = {
    "job": AgentAction,
    "thread": AgentThread,
    "invoice": Invoice,
    "internal_thread": InternalThread,
    "deepblue_conversation": DeepBlueConversation,
}

# Subject words to ignore when matching
_STOP_WORDS = {"re", "fwd", "fw", "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "at", "is"}


from src.utils.thread_utils import normalize_subject as _normalize_subject


def _subject_overlap(a: str, b: str) -> bool:
    """Check if two subjects share meaningful words."""
    words_a = {w for w in _normalize_subject(a).split() if w not in _STOP_WORDS and len(w) > 2}
    words_b = {w for w in _normalize_subject(b).split() if w not in _STOP_WORDS and len(w) > 2}
    if not words_a or not words_b:
        return False
    overlap = words_a & words_b
    return len(overlap) >= min(2, min(len(words_a), len(words_b)))


class ServiceCaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def next_case_number(self, org_id: str) -> str:
        """Generate SC-YY-NNNN case number."""
        year = datetime.now(timezone.utc).strftime("%y")
        prefix = f"SC-{year}-"
        result = await self.db.execute(
            select(func.max(ServiceCase.case_number)).where(
                ServiceCase.organization_id == org_id,
                ServiceCase.case_number.like(f"{prefix}%"),
            )
        )
        last = result.scalar()
        if last:
            try:
                seq = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"

    async def create(
        self,
        org_id: str,
        title: str,
        source: str,
        customer_id: str | None = None,
        billing_name: str | None = None,
        status: str = "new",
        priority: str = "normal",
        created_by: str | None = None,
    ) -> ServiceCase:
        case = ServiceCase(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            customer_id=customer_id,
            billing_name=billing_name if not customer_id else None,
            case_number=await self.next_case_number(org_id),
            title=title[:300],
            status=status,
            priority=priority,
            source=source,
            created_by=created_by,
            manager_name=created_by,
            current_actor_name=created_by,
        )
        self.db.add(case)
        await self.db.flush()
        return case

    async def get(self, org_id: str, case_id: str) -> ServiceCase | None:
        result = await self.db.execute(
            select(ServiceCase).where(
                ServiceCase.id == case_id,
                ServiceCase.organization_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_or_create_case(
        self,
        org_id: str,
        customer_id: str | None,
        thread_id: str | None,
        subject: str,
        source: str,
        created_by: str | None = None,
    ) -> ServiceCase:
        """Find an existing open case to attach to, or create a new one.

        Matching rules (deterministic, no AI):
        1. Thread already has case_id → use it
        2. Same customer has open case with matching subject → use it
        3. Same customer has exactly 1 open case in last 14 days → use it
        4. No match → create new case
        """
        # Rule 1: Thread already has a case
        if thread_id:
            thread = await self.db.get(AgentThread, thread_id)
            if thread and thread.case_id:
                case = await self.db.get(ServiceCase, thread.case_id)
                if case:
                    return case

        if not customer_id:
            return await self.create(
                org_id=org_id,
                title=_normalize_subject(subject).title() or "New Case",
                source=source,
                customer_id=None,
                created_by=created_by,
            )

        # Rule 2: Open case with matching subject for same customer
        open_cases_result = await self.db.execute(
            select(ServiceCase).where(
                ServiceCase.organization_id == org_id,
                ServiceCase.customer_id == customer_id,
                ServiceCase.status.not_in(["closed", "cancelled"]),
            ).order_by(ServiceCase.updated_at.desc()).limit(10)
        )
        open_cases = open_cases_result.scalars().all()

        for case in open_cases:
            if _subject_overlap(case.title, subject):
                return case

        # Rule 3: Exactly one open case in last 14 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        recent = [c for c in open_cases if c.updated_at and c.updated_at >= cutoff]
        if len(recent) == 1:
            return recent[0]

        # Rule 4: Create new case
        return await self.create(
            org_id=org_id,
            title=_normalize_subject(subject).title() or "New Case",
            source=source,
            customer_id=customer_id,
            created_by=created_by,
        )

    async def update_counts(self, case_id: str) -> None:
        """Recalculate denormalized counts from child entities."""
        case = await self.db.get(ServiceCase, case_id)
        if not case:
            return

        # Jobs
        job_result = await self.db.execute(
            select(
                func.count(AgentAction.id),
                func.count(AgentAction.id).filter(AgentAction.status.in_(["open", "in_progress", "suggested"])),
            ).where(AgentAction.case_id == case_id)
        )
        row = job_result.one()
        case.job_count = row[0]
        case.open_job_count = row[1]

        # Threads
        thread_result = await self.db.execute(
            select(func.count(AgentThread.id)).where(AgentThread.case_id == case_id)
        )
        case.thread_count = thread_result.scalar() or 0

        # Invoices
        inv_result = await self.db.execute(
            select(
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.total), 0),
                func.coalesce(func.sum(Invoice.amount_paid), 0),
            ).where(Invoice.case_id == case_id)
        )
        inv_row = inv_result.one()
        case.invoice_count = inv_row[0]
        case.total_invoiced = float(inv_row[1])
        case.total_paid = float(inv_row[2])

        # Internal threads
        it_count = (await self.db.execute(
            select(func.count(InternalThread.id)).where(InternalThread.case_id == case_id)
        )).scalar() or 0
        case.internal_thread_count = it_count

        # DeepBlue conversations
        db_count = (await self.db.execute(
            select(func.count(DeepBlueConversation.id)).where(DeepBlueConversation.case_id == case_id)
        )).scalar() or 0
        case.deepblue_conversation_count = db_count

        case.updated_at = datetime.now(timezone.utc)

    async def set_entity_case(
        self,
        org_id: str,
        entity_type: str,
        entity_id: str,
        new_case_id: str | None,
        user_name: str | None = None,
    ) -> dict:
        """Authoritative entry point for linking/unlinking entities to cases.

        Every code path that mutates `<entity>.case_id` MUST route through here.
        Handles:
          - Cross-org safety (org-scoped entity lookup + target case lookup)
          - Prior-case count refresh (so detaching updates the source case)
          - New-case count refresh (so attaching updates the target)
          - Activity log entry on the linked job (if any)
          - `case.updated` real-time event publish for both affected cases

        Returns dict describing the transition. Raises on validation error.
        """
        model = LINKABLE_MODELS.get(entity_type)
        if not model:
            raise ValueError(f"unknown linkable entity type: {entity_type}")

        entity = (await self.db.execute(
            select(model).where(model.id == entity_id, model.organization_id == org_id)
        )).scalar_one_or_none()
        if not entity:
            raise LookupError(f"{entity_type} not found")

        prior_case_id = entity.case_id

        if new_case_id:
            target_case = (await self.db.execute(
                select(ServiceCase).where(
                    ServiceCase.id == new_case_id,
                    ServiceCase.organization_id == org_id,
                )
            )).scalar_one_or_none()
            if not target_case:
                raise LookupError("target case not found")

        # Idempotent: same case → no-op.
        if prior_case_id == new_case_id:
            return {"changed": False, "prior_case_id": prior_case_id, "new_case_id": new_case_id}

        entity.case_id = new_case_id
        await self.db.flush()

        if prior_case_id:
            await self.update_counts(prior_case_id)
        if new_case_id:
            await self.update_counts(new_case_id)

        # Activity log — best-effort. Log on the linked job (for invoice→job
        # chain) or on any job sharing the thread for thread-type links.
        try:
            await self._log_link_activity(entity_type, entity, prior_case_id, new_case_id, user_name)
        except Exception:  # pragma: no cover
            logger.warning("link activity log failed", exc_info=True)

        # Fire real-time events for both affected cases so open UIs refresh.
        from src.core.events import EventType, publish
        payload = {"entity_type": entity_type, "entity_id": entity_id}
        if prior_case_id:
            try:
                await publish(EventType.CASE_UPDATED, org_id, {"case_id": prior_case_id, "action": "unlinked", **payload})
            except Exception:
                logger.warning("publish CASE_UPDATED (unlink) failed", exc_info=True)
        if new_case_id:
            try:
                await publish(EventType.CASE_UPDATED, org_id, {"case_id": new_case_id, "action": "linked", **payload})
            except Exception:
                logger.warning("publish CASE_UPDATED (link) failed", exc_info=True)

        return {
            "changed": True,
            "prior_case_id": prior_case_id,
            "new_case_id": new_case_id,
        }

    async def _log_link_activity(
        self,
        entity_type: str,
        entity,
        prior_case_id: str | None,
        new_case_id: str | None,
        user_name: str | None,
    ) -> None:
        """Leave a trail on a job attached to the same target case so the case
        timeline shows the link event. If there's no job to attach to, we skip —
        activity logs on cases without jobs are a Phase 5 concern.
        """
        target_case_id = new_case_id or prior_case_id
        if not target_case_id:
            return
        # Find any job currently attached to the target case to host the comment.
        host_job = (await self.db.execute(
            select(AgentAction).where(AgentAction.case_id == target_case_id).limit(1)
        )).scalar_one_or_none()
        if not host_job:
            return

        who = user_name or "System"
        if new_case_id and prior_case_id:
            msg = f"{who} moved {entity_type} {entity.id[:8]} from case {prior_case_id[:8]} to case {new_case_id[:8]}"
        elif new_case_id:
            msg = f"{who} linked {entity_type} {entity.id[:8]} to this case"
        else:
            msg = f"{who} unlinked {entity_type} {entity.id[:8]} from this case"

        self.db.add(AgentActionComment(
            id=str(uuid.uuid4()),
            organization_id=host_job.organization_id,
            action_id=host_job.id,
            author="System",
            text=f"[ACTIVITY]\n{msg}",
        ))

    async def update_status_from_children(self, case_id: str) -> None:
        """Auto-advance case status, compute flags, and derive current actor.

        Called after any job status change, invoice send/pay, or estimate approval.
        """
        case = await self.db.get(ServiceCase, case_id)
        if not case or case.status in ("closed", "cancelled"):
            # Closed/cancelled are terminal. Re-deriving from children would
            # undo a deliberate human close (e.g., writing off an open invoice
            # then closing the case would flip back to pending_payment).
            # Users can explicitly reopen via PUT /cases/{id} with a non-terminal status.
            return

        # Load child states — jobs with assignees
        job_rows = (await self.db.execute(
            select(AgentAction.status, AgentAction.assigned_to)
            .where(AgentAction.case_id == case_id)
        )).all()
        job_statuses = [r[0] for r in job_rows]

        # Threads with assignment and pending status
        thread_rows = (await self.db.execute(
            select(AgentThread.has_pending, AgentThread.assigned_to_name, AgentThread.last_direction)
            .where(AgentThread.case_id == case_id)
        )).all()

        # Invoices and estimates
        invoice_rows = (await self.db.execute(
            select(Invoice.status, Invoice.document_type, Invoice.due_date, Invoice.amount_paid)
            .where(Invoice.case_id == case_id)
        )).all()

        estimate_statuses = [i[0] for i in invoice_rows if i[1] == "estimate"]
        invoice_statuses = [i[0] for i in invoice_rows if i[1] == "invoice"]

        # --- Status derivation (same logic as before) ---
        all_jobs_done = job_statuses and all(s in ("done", "cancelled") for s in job_statuses)
        any_job_in_progress = any(s == "in_progress" for s in job_statuses)
        has_sent_invoice = any(s in ("sent", "overdue") for s in invoice_statuses)
        all_invoices_paid = invoice_statuses and all(s in ("paid", "void", "written_off") for s in invoice_statuses)
        has_approved_estimate = "approved" in estimate_statuses
        has_rejected_estimate = "rejected" in estimate_statuses
        has_sent_estimate = any(s in ("sent", "revised", "viewed") for s in estimate_statuses)

        # Cases close once the work is done and an invoice has been issued.
        # Payment collection (30-45 days of AR waiting) is tracked by the
        # invoice itself, not by keeping the case in a pending_payment limbo
        # that clutters the active case list. If the invoice goes overdue,
        # flag_invoice_overdue still fires on the closed case so reports can
        # find it; users can reopen the case if a dispute arises.
        if all_jobs_done and (all_invoices_paid or has_sent_invoice) and invoice_statuses:
            new_status = "closed"
        elif any_job_in_progress or (has_approved_estimate and job_statuses):
            new_status = "in_progress"
        elif has_approved_estimate:
            new_status = "approved"
        elif has_sent_estimate:
            new_status = "pending_approval"
        elif estimate_statuses:
            new_status = "scoping"
        elif job_statuses:
            new_status = "in_progress" if any_job_in_progress else case.status
        else:
            new_status = case.status

        if new_status != case.status:
            case.status = new_status
            if new_status == "closed":
                case.closed_at = datetime.now(timezone.utc)
            elif case.closed_at:
                case.closed_at = None

        # --- Flags (all must be explicit bool) ---
        # Estimate approved: cleared when a job exists for the approved work
        case.flag_estimate_approved = bool(has_approved_estimate and not any_job_in_progress and not all_jobs_done)

        # Estimate rejected
        case.flag_estimate_rejected = bool(has_rejected_estimate)

        # Payment received: any invoice fully paid but case not yet closed
        case.flag_payment_received = bool(all_invoices_paid and invoice_statuses and new_status != "closed")

        # Customer replied: thread has pending inbound message
        case.flag_customer_replied = bool(any(
            r[0] and r[2] == "inbound"  # has_pending and last_direction == inbound
            for r in thread_rows
        ))

        # All jobs complete but case still open (need to invoice or close)
        case.flag_jobs_complete = bool(all_jobs_done and job_statuses and new_status != "closed")

        # Invoice overdue
        now_date = datetime.now(timezone.utc).date()
        case.flag_invoice_overdue = bool(any(
            i[0] in ("sent", "overdue") and i[2] and i[2] < now_date
            for i in invoice_rows if i[1] == "invoice"
        ))

        # Stale: no update in 7+ days on open case
        case.flag_stale = bool(
            case.updated_at is not None
            and (datetime.now(timezone.utc) - case.updated_at) > timedelta(days=7)
            and new_status not in ("closed", "cancelled")
        )

        # --- Current actor ---
        # Priority: open job assignee > pending thread assignee > awaiting customer > manager
        actor = None

        # 1. Open/in-progress job with an assignee
        for status, assigned_to in job_rows:
            if status in ("open", "in_progress") and assigned_to:
                actor = assigned_to
                break

        # 2. Pending thread with an assignee
        if not actor:
            for has_pending, assigned_name, _ in thread_rows:
                if has_pending and assigned_name:
                    actor = assigned_name
                    break

        # 3. Waiting on customer (estimate sent or invoice sent)
        if not actor and (has_sent_estimate or has_sent_invoice):
            actor = "Awaiting customer"

        # 4. Fall back to manager
        if not actor:
            actor = case.manager_name

        case.current_actor_name = actor

        await self.update_counts(case_id)

    async def list_cases(
        self,
        org_id: str,
        status: str | None = None,
        customer_id: str | None = None,
        search: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        query = select(ServiceCase).where(ServiceCase.organization_id == org_id)

        if status:
            query = query.where(ServiceCase.status == status)
        if customer_id:
            query = query.where(ServiceCase.customer_id == customer_id)
        if search:
            query = query.where(
                ServiceCase.title.ilike(f"%{search}%")
                | ServiceCase.case_number.ilike(f"%{search}%")
            )

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(ServiceCase.updated_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        cases = result.scalars().all()

        return {"items": cases, "total": total}
