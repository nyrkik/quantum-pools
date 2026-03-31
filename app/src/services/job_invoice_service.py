"""Job-Invoice linking service — single source of truth for job↔invoice/estimate relationships."""

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.models.job_invoice import JobInvoice
from src.models.agent_action import AgentAction


async def link_job_invoice(db: AsyncSession, action_id: str, invoice_id: str, linked_by: str | None = None) -> None:
    """Link a job to an invoice/estimate. Idempotent — won't duplicate."""
    existing = await db.execute(
        select(JobInvoice).where(
            JobInvoice.action_id == action_id,
            JobInvoice.invoice_id == invoice_id,
        )
    )
    if existing.scalar_one_or_none():
        return
    db.add(JobInvoice(
        id=str(uuid.uuid4()),
        action_id=action_id,
        invoice_id=invoice_id,
        linked_by=linked_by,
    ))


async def unlink_job_invoice(db: AsyncSession, action_id: str, invoice_id: str) -> None:
    """Remove link between a job and an invoice/estimate."""
    await db.execute(
        delete(JobInvoice).where(
            JobInvoice.action_id == action_id,
            JobInvoice.invoice_id == invoice_id,
        )
    )


async def get_jobs_for_invoice(db: AsyncSession, invoice_id: str) -> list[AgentAction]:
    """Get all jobs linked to an invoice/estimate."""
    result = await db.execute(
        select(AgentAction)
        .join(JobInvoice, JobInvoice.action_id == AgentAction.id)
        .where(JobInvoice.invoice_id == invoice_id)
    )
    return list(result.scalars().all())


async def get_invoices_for_job(db: AsyncSession, action_id: str) -> list[str]:
    """Get all invoice IDs linked to a job."""
    result = await db.execute(
        select(JobInvoice.invoice_id).where(JobInvoice.action_id == action_id)
    )
    return [r[0] for r in result.all()]


async def get_first_job_for_invoice(db: AsyncSession, invoice_id: str) -> AgentAction | None:
    """Get the first job linked to an invoice (for backward compat)."""
    result = await db.execute(
        select(AgentAction)
        .join(JobInvoice, JobInvoice.action_id == AgentAction.id)
        .where(JobInvoice.invoice_id == invoice_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def unlink_all_for_invoice(db: AsyncSession, invoice_id: str) -> None:
    """Remove all job links for an invoice (used on draft delete)."""
    await db.execute(
        delete(JobInvoice).where(JobInvoice.invoice_id == invoice_id)
    )
