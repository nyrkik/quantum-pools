"""Backfill ServiceCases from existing threads, jobs, and invoices.

Idempotent — skips entities that already have a case_id.
Safe to re-run if interrupted.

Usage: cd /srv/quantumpools/app && /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_cases.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import uuid
import logging
from datetime import datetime, timezone
from collections import defaultdict

from sqlalchemy import select, text, update
from sqlalchemy.orm import selectinload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill():
    from src.core.database import get_db_context
    from src.models.service_case import ServiceCase
    from src.models.agent_thread import AgentThread
    from src.models.agent_action import AgentAction
    from src.models.invoice import Invoice
    from src.models.job_invoice import JobInvoice
    from src.models.internal_message import InternalThread
    from src.services.service_case_service import ServiceCaseService

    async with get_db_context() as db:
        # Get the org_id (single-org system for now)
        org_id = (await db.execute(text("SELECT id FROM organizations LIMIT 1"))).scalar()
        if not org_id:
            logger.error("No organization found")
            return

        svc = ServiceCaseService(db)
        created = 0
        linked_threads = 0
        linked_jobs = 0
        linked_invoices = 0
        linked_internal = 0

        # ===== PHASE A: Thread-anchored cases =====
        logger.info("Phase A: Creating cases from threads...")
        threads = (await db.execute(
            select(AgentThread).where(
                AgentThread.organization_id == org_id,
                AgentThread.case_id.is_(None),
            ).order_by(AgentThread.created_at)
        )).scalars().all()

        for t in threads:
            # Create a case for this thread
            case = await svc.create(
                org_id=org_id,
                title=(t.subject or t.customer_name or "Email Thread")[:300],
                source="email",
                customer_id=t.matched_customer_id,
                status="closed" if t.status == "handled" else "new",
                created_by="backfill",
            )
            t.case_id = case.id
            linked_threads += 1
            created += 1

            # Link all jobs that reference this thread
            jobs = (await db.execute(
                select(AgentAction).where(
                    AgentAction.thread_id == t.id,
                    AgentAction.case_id.is_(None),
                )
            )).scalars().all()
            for j in jobs:
                j.case_id = case.id
                linked_jobs += 1

                # Link invoices connected to this job via job_invoices
                job_inv_result = await db.execute(
                    select(JobInvoice.invoice_id).where(JobInvoice.action_id == j.id)
                )
                for (inv_id,) in job_inv_result.all():
                    inv = await db.get(Invoice, inv_id)
                    if inv and not inv.case_id:
                        inv.case_id = case.id
                        linked_invoices += 1

            if created % 50 == 0 and created > 0:
                logger.info(f"  Progress: {created} cases created...")
                await db.commit()

        await db.commit()
        logger.info(f"Phase A done: {created} cases, {linked_threads} threads, {linked_jobs} jobs, {linked_invoices} invoices")

        # ===== PHASE B: Orphan jobs (no thread, no case) =====
        logger.info("Phase B: Creating cases from orphan jobs...")
        orphan_jobs = (await db.execute(
            select(AgentAction).where(
                AgentAction.organization_id == org_id,
                AgentAction.thread_id.is_(None),
                AgentAction.case_id.is_(None),
            ).order_by(AgentAction.created_at)
        )).scalars().all()

        # Group by customer_id + week
        groups = defaultdict(list)
        for j in orphan_jobs:
            week_key = j.created_at.strftime("%Y-W%W") if j.created_at else "unknown"
            group_key = f"{j.customer_id or 'no-customer'}|{week_key}"
            groups[group_key].append(j)

        orphan_created = 0
        for group_key, jobs in groups.items():
            title = jobs[0].description[:300] if jobs[0].description else "Manual Job"
            customer_id = jobs[0].customer_id

            # Check if this customer already has an open case we can attach to
            existing = None
            if customer_id:
                existing_result = await db.execute(
                    select(ServiceCase).where(
                        ServiceCase.organization_id == org_id,
                        ServiceCase.customer_id == customer_id,
                        ServiceCase.status.not_in(["closed", "cancelled"]),
                    ).limit(1)
                )
                existing = existing_result.scalar_one_or_none()

            if existing:
                case = existing
            else:
                all_done = all(j.status in ("done", "cancelled") for j in jobs)
                case = await svc.create(
                    org_id=org_id,
                    title=title,
                    source="manual",
                    customer_id=customer_id,
                    status="closed" if all_done else "new",
                    created_by="backfill",
                )
                orphan_created += 1
                created += 1

            for j in jobs:
                j.case_id = case.id
                linked_jobs += 1

                # Also check for linked invoices
                job_inv_result = await db.execute(
                    select(JobInvoice.invoice_id).where(JobInvoice.action_id == j.id)
                )
                for (inv_id,) in job_inv_result.all():
                    inv = await db.get(Invoice, inv_id)
                    if inv and not inv.case_id:
                        inv.case_id = case.id
                        linked_invoices += 1

        await db.commit()
        logger.info(f"Phase B done: {orphan_created} new cases for {len(orphan_jobs)} orphan jobs")

        # ===== PHASE C: Orphan invoices =====
        logger.info("Phase C: Linking orphan invoices...")
        orphan_invs = (await db.execute(
            select(Invoice).where(
                Invoice.organization_id == org_id,
                Invoice.case_id.is_(None),
            )
        )).scalars().all()

        inv_created = 0
        for inv in orphan_invs:
            # Try to find via job_invoices
            ji_result = await db.execute(
                select(JobInvoice.action_id).where(JobInvoice.invoice_id == inv.id).limit(1)
            )
            action_id = ji_result.scalar()
            if action_id:
                action = await db.get(AgentAction, action_id)
                if action and action.case_id:
                    inv.case_id = action.case_id
                    linked_invoices += 1
                    continue

            # Create standalone case
            case = await svc.create(
                org_id=org_id,
                title=(inv.subject or f"Invoice {inv.invoice_number or 'Draft'}")[:300],
                source="manual",
                customer_id=inv.customer_id,
                status="closed" if inv.status in ("paid", "void", "written_off") else "new",
                created_by="backfill",
            )
            inv.case_id = case.id
            linked_invoices += 1
            inv_created += 1
            created += 1

        await db.commit()
        logger.info(f"Phase C done: {inv_created} new cases for {len(orphan_invs)} orphan invoices")

        # ===== PHASE D: Internal threads =====
        logger.info("Phase D: Linking internal threads...")
        int_threads = (await db.execute(
            select(InternalThread).where(
                InternalThread.organization_id == org_id,
                InternalThread.case_id.is_(None),
            )
        )).scalars().all()

        for it in int_threads:
            # If it has an action_id, inherit that action's case
            if it.action_id:
                action = await db.get(AgentAction, it.action_id)
                if action and action.case_id:
                    it.case_id = action.case_id
                    linked_internal += 1
                    continue
            # If it has a customer_id, try to find a recent case
            if it.customer_id:
                existing_result = await db.execute(
                    select(ServiceCase).where(
                        ServiceCase.organization_id == org_id,
                        ServiceCase.customer_id == it.customer_id,
                    ).order_by(ServiceCase.updated_at.desc()).limit(1)
                )
                existing = existing_result.scalar_one_or_none()
                if existing:
                    it.case_id = existing.id
                    linked_internal += 1

        await db.commit()
        logger.info(f"Phase D done: {linked_internal} internal threads linked")

        # ===== PHASE E: Recalculate counts =====
        logger.info("Phase E: Recalculating case counts...")
        all_cases = (await db.execute(
            select(ServiceCase).where(ServiceCase.organization_id == org_id)
        )).scalars().all()

        for case in all_cases:
            await svc.update_counts(case.id)

        await db.commit()
        logger.info(f"Phase E done: {len(all_cases)} cases updated")

        # ===== SUMMARY =====
        logger.info("=" * 50)
        logger.info(f"Backfill complete:")
        logger.info(f"  Cases created: {created}")
        logger.info(f"  Threads linked: {linked_threads}")
        logger.info(f"  Jobs linked: {linked_jobs}")
        logger.info(f"  Invoices linked: {linked_invoices}")
        logger.info(f"  Internal threads linked: {linked_internal}")

        # Verify no orphans
        orphan_check = {
            "agent_actions": (await db.execute(text("SELECT COUNT(*) FROM agent_actions WHERE case_id IS NULL AND organization_id = :oid"), {"oid": org_id})).scalar(),
            "agent_threads": (await db.execute(text("SELECT COUNT(*) FROM agent_threads WHERE case_id IS NULL AND organization_id = :oid"), {"oid": org_id})).scalar(),
            "invoices": (await db.execute(text("SELECT COUNT(*) FROM invoices WHERE case_id IS NULL AND organization_id = :oid"), {"oid": org_id})).scalar(),
        }
        logger.info(f"  Remaining orphans: {orphan_check}")


if __name__ == "__main__":
    asyncio.run(backfill())
