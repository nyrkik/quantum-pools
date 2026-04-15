"""Repair case-link drift: threads/jobs that should share a case but don't.

Passes:
  1. Threads that have jobs but no case → find-or-create a case, attach thread + all its jobs.
  2. Jobs whose thread is already in a case but the job itself is not → link job to thread's case.
  3. Orphan jobs (no thread, no case) that have a customer and are not terminal → find-or-create
     a case for the customer, attach. Terminal jobs (done/cancelled) are skipped — no value in
     wrapping completed standalone work in a case.

Idempotent via ServiceCaseService.set_entity_case (same-case → no-op).

Usage:
  cd /srv/quantumpools/app && \
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_case_links.py --dry-run
  # then, after reviewing:
  /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_case_links.py --apply
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_case_links")


TERMINAL_JOB_STATUSES = {"done", "cancelled", "completed"}


async def run(dry_run: bool) -> None:
    from src.core.database import get_db_context
    from src.models.agent_thread import AgentThread
    from src.models.agent_action import AgentAction
    from src.services.service_case_service import ServiceCaseService

    async with get_db_context() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations LIMIT 1"))).scalar()
        if not org_id:
            logger.error("No organization found")
            return
        svc = ServiceCaseService(db)

        # ---------- PASS 1: threads with jobs but no case ----------
        rows = (await db.execute(
            select(AgentThread).where(
                AgentThread.organization_id == org_id,
                AgentThread.case_id.is_(None),
                AgentThread.id.in_(
                    select(AgentAction.thread_id).where(AgentAction.thread_id.is_not(None)).distinct()
                ),
            )
        )).scalars().all()
        logger.info("Pass 1: %d threads with jobs but no case", len(rows))
        p1_threads_linked = 0
        p1_jobs_linked = 0
        for thread in rows:
            # All jobs on this thread
            jobs = (await db.execute(
                select(AgentAction).where(
                    AgentAction.organization_id == org_id,
                    AgentAction.thread_id == thread.id,
                )
            )).scalars().all()
            if dry_run:
                logger.info(
                    "  [dry] thread %s (%r, cust=%s) → would create/attach case + %d job(s): %s",
                    thread.id, (thread.subject or "")[:60], thread.matched_customer_id,
                    len(jobs), ", ".join(f"{j.id}:{j.status}" for j in jobs),
                )
                p1_threads_linked += 1
                p1_jobs_linked += len(jobs)
                continue
            case = await svc.find_or_create_case(
                org_id=org_id,
                customer_id=thread.matched_customer_id,
                thread_id=thread.id,
                subject=thread.subject or "(no subject)",
                source="backfill",
                created_by="backfill_case_links",
            )
            await db.flush()
            await svc.set_entity_case(
                org_id=org_id, entity_type="thread", entity_id=thread.id,
                new_case_id=case.id, user_name="backfill_case_links",
            )
            p1_threads_linked += 1
            for job in jobs:
                if job.case_id == case.id:
                    continue
                await svc.set_entity_case(
                    org_id=org_id, entity_type="job", entity_id=job.id,
                    new_case_id=case.id, user_name="backfill_case_links",
                )
                p1_jobs_linked += 1
            await db.commit()
        logger.info("Pass 1 result: %d threads linked, %d jobs linked",
                    p1_threads_linked, p1_jobs_linked)

        # ---------- PASS 2: jobs whose thread is in a case but job isn't ----------
        rows = (await db.execute(
            select(AgentAction, AgentThread.case_id)
            .join(AgentThread, AgentThread.id == AgentAction.thread_id)
            .where(
                AgentAction.organization_id == org_id,
                AgentAction.case_id.is_(None),
                AgentThread.case_id.is_not(None),
            )
        )).all()
        logger.info("Pass 2: %d jobs whose thread has a case but the job doesn't", len(rows))
        p2_jobs_linked = 0
        for job, target_case_id in rows:
            if dry_run:
                logger.info(
                    "  [dry] job %s (%r, status=%s) → would attach to case %s",
                    job.id, (job.description or "")[:60], job.status, target_case_id,
                )
                p2_jobs_linked += 1
                continue
            await svc.set_entity_case(
                org_id=org_id, entity_type="job", entity_id=job.id,
                new_case_id=target_case_id, user_name="backfill_case_links",
            )
            p2_jobs_linked += 1
            await db.commit()
        logger.info("Pass 2 result: %d jobs linked", p2_jobs_linked)

        # ---------- PASS 3: orphan jobs (no thread, no case) ----------
        rows = (await db.execute(
            select(AgentAction).where(
                AgentAction.organization_id == org_id,
                AgentAction.case_id.is_(None),
                AgentAction.thread_id.is_(None),
            )
        )).scalars().all()
        logger.info("Pass 3: %d orphan jobs (no thread, no case)", len(rows))
        p3_jobs_linked = 0
        p3_skipped_terminal = 0
        p3_skipped_no_customer = 0
        for job in rows:
            if (job.status or "").lower() in TERMINAL_JOB_STATUSES:
                logger.info("  skip terminal job %s (status=%s)", job.id, job.status)
                p3_skipped_terminal += 1
                continue
            if not job.customer_id:
                logger.warning("  skip job %s — no customer; needs manual triage", job.id)
                p3_skipped_no_customer += 1
                continue
            if dry_run:
                logger.info(
                    "  [dry] job %s (%r, cust=%s) → would create/attach case",
                    job.id, (job.description or "")[:60], job.customer_id,
                )
                p3_jobs_linked += 1
                continue
            case = await svc.find_or_create_case(
                org_id=org_id,
                customer_id=job.customer_id,
                thread_id=None,
                subject=job.description or "Standalone job",
                source="backfill",
                created_by="backfill_case_links",
            )
            await db.flush()
            await svc.set_entity_case(
                org_id=org_id, entity_type="job", entity_id=job.id,
                new_case_id=case.id, user_name="backfill_case_links",
            )
            p3_jobs_linked += 1
            await db.commit()
        logger.info("Pass 3 result: %d linked, %d skipped terminal, %d skipped no-customer",
                    p3_jobs_linked, p3_skipped_terminal, p3_skipped_no_customer)

        # ---------- Final drift check ----------
        remaining = (await db.execute(text("""
            SELECT 'threads_with_jobs_no_case' AS m, COUNT(DISTINCT t.id) AS n
              FROM agent_threads t JOIN agent_actions aa ON aa.thread_id = t.id
             WHERE t.case_id IS NULL
            UNION ALL
            SELECT 'jobs_no_case_with_thread', COUNT(*)
              FROM agent_actions WHERE case_id IS NULL AND thread_id IS NOT NULL
            UNION ALL
            SELECT 'jobs_no_case_no_thread_open', COUNT(*)
              FROM agent_actions
             WHERE case_id IS NULL AND thread_id IS NULL AND LOWER(status) NOT IN ('done','cancelled','completed')
            UNION ALL
            SELECT 'threads_with_case_but_jobs_without', COUNT(DISTINCT aa.id)
              FROM agent_threads t JOIN agent_actions aa ON aa.thread_id = t.id
             WHERE t.case_id IS NOT NULL AND aa.case_id IS NULL
            UNION ALL
            SELECT 'threads_and_jobs_case_mismatch', COUNT(DISTINCT aa.id)
              FROM agent_threads t JOIN agent_actions aa ON aa.thread_id = t.id
             WHERE t.case_id IS NOT NULL AND aa.case_id IS NOT NULL AND t.case_id != aa.case_id
        """))).all()
        logger.info("Final drift:")
        for m, n in remaining:
            logger.info("  %s = %s", m, n)


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Log planned changes only; no DB writes.")
    g.add_argument("--apply", action="store_true", help="Apply changes.")
    args = p.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
