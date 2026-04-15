"""Recompute denormalized counts on every ServiceCase via the authoritative service method.

Run after any direct DB delete of agent_actions / threads / invoices that bypassed
ServiceCaseService. Idempotent and safe to re-run.

Usage: cd /srv/quantumpools/app && /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/refresh_case_counts.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import select


async def run():
    from src.core.database import get_db_context
    from src.models.service_case import ServiceCase
    from src.services.service_case_service import ServiceCaseService

    async with get_db_context() as db:
        cases = (await db.execute(select(ServiceCase.id))).scalars().all()
        svc = ServiceCaseService(db)
        for cid in cases:
            await svc.update_counts(cid)
        await db.commit()
        print(f"refreshed {len(cases)} cases")


if __name__ == "__main__":
    asyncio.run(run())
