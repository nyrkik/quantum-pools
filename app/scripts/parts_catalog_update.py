#!/usr/bin/env python3
"""Weekly parts catalog update — discovers parts for new equipment models.

Run manually:
    cd /srv/quantumpools/app
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python -m scripts.parts_catalog_update

Or via cron/systemd timer for weekly execution.
"""

import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def run():
    """Discover parts for all orgs with unmatched equipment models."""
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.organization import Organization
    from src.services.parts.equipment_parts_agent import EquipmentPartsAgent

    logger.info("Parts catalog update started")
    total_parts = 0
    total_models = 0

    async with get_db_context() as db:
        result = await db.execute(select(Organization.id, Organization.name))
        orgs = result.all()

    for org_id, org_name in orgs:
        logger.info(f"Scanning org: {org_name} ({org_id})")
        try:
            async with get_db_context() as db:
                agent = EquipmentPartsAgent(db)
                result = await agent.discover_parts_for_org(org_id)
            total_parts += result["parts_discovered"]
            total_models += result["new_models_found"]
            logger.info(
                f"  {org_name}: scanned {result['models_scanned']} models, "
                f"{result['new_models_found']} new, {result['parts_discovered']} parts discovered"
            )
            if result.get("errors"):
                logger.warning(f"  {org_name}: {result['errors']} errors during discovery")
        except Exception as e:
            logger.error(f"  {org_name}: failed — {e}")

    logger.info(f"Parts catalog update complete: {total_models} new models, {total_parts} parts discovered")


if __name__ == "__main__":
    asyncio.run(run())
