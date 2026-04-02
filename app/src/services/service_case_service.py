"""ServiceCase service — CRUD, matching, status management."""

import uuid
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.service_case import ServiceCase
from src.models.agent_action import AgentAction
from src.models.agent_thread import AgentThread
from src.models.invoice import Invoice

logger = logging.getLogger(__name__)

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
        status: str = "new",
        priority: str = "normal",
        created_by: str | None = None,
    ) -> ServiceCase:
        case = ServiceCase(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            customer_id=customer_id,
            case_number=await self.next_case_number(org_id),
            title=title[:300],
            status=status,
            priority=priority,
            source=source,
            created_by=created_by,
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

        case.updated_at = datetime.now(timezone.utc)

    async def update_status_from_children(self, case_id: str) -> None:
        """Auto-advance case status based on child entity states.

        Called after any job status change, invoice send/pay, or estimate approval.
        """
        case = await self.db.get(ServiceCase, case_id)
        if not case or case.status in ("cancelled",):
            return

        # Load child states
        jobs = (await self.db.execute(
            select(AgentAction.status).where(AgentAction.case_id == case_id)
        )).scalars().all()

        invoices = (await self.db.execute(
            select(Invoice.status, Invoice.document_type).where(Invoice.case_id == case_id)
        )).all()

        estimate_statuses = [i[0] for i in invoices if i[1] == "estimate"]
        invoice_statuses = [i[0] for i in invoices if i[1] == "invoice"]

        all_jobs_done = jobs and all(s in ("done", "cancelled") for s in jobs)
        any_job_in_progress = any(s == "in_progress" for s in jobs)
        has_sent_invoice = any(s in ("sent", "overdue") for s in invoice_statuses)
        all_invoices_paid = invoice_statuses and all(s in ("paid", "void", "written_off") for s in invoice_statuses)
        has_approved_estimate = "approved" in estimate_statuses
        has_sent_estimate = any(s in ("sent", "revised", "viewed") for s in estimate_statuses)

        # Determine new status (priority order)
        if all_jobs_done and all_invoices_paid and invoice_statuses:
            new_status = "closed"
        elif all_jobs_done and has_sent_invoice:
            new_status = "pending_payment"
        elif any_job_in_progress or (has_approved_estimate and jobs):
            new_status = "in_progress"
        elif has_approved_estimate:
            new_status = "approved"
        elif has_sent_estimate:
            new_status = "pending_approval"
        elif estimate_statuses:
            new_status = "scoping"
        elif jobs:
            new_status = "in_progress" if any_job_in_progress else case.status
        else:
            new_status = case.status

        if new_status != case.status:
            case.status = new_status
            if new_status == "closed":
                case.closed_at = datetime.now(timezone.utc)
            elif case.closed_at:
                case.closed_at = None

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
