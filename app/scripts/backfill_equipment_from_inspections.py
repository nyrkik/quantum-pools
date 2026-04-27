#!/usr/bin/env python
"""Backfill `equipment_items` from existing `inspection_equipment` data.

Iterates every matched `InspectionFacility` for the target org(s), calls
`InspectionService.sync_equipment_to_bow(facility_id)` for each, and reports
counts. Idempotent — safe to re-run; existing rows update in place via the
`(water_feature_id, source_inspection_id, source_slot)` upsert key.

Usage:
    python scripts/backfill_equipment_from_inspections.py --org-id <uuid>
    python scripts/backfill_equipment_from_inspections.py --all-orgs
    python scripts/backfill_equipment_from_inspections.py --org-id <uuid> --dry-run

Run from the `app/` directory using the project venv:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_equipment_from_inspections.py --org-id 7ef7ab72-703f-45c1-847f-565101cb3e61
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.inspection_facility import InspectionFacility
from src.models.organization import Organization
from src.services.inspection.service import InspectionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill_equipment_from_inspections")


async def backfill_one_org(db: AsyncSession, org_id: str, dry_run: bool) -> dict:
    """Process all matched facilities for a single org."""
    result = await db.execute(
        select(InspectionFacility).where(
            InspectionFacility.organization_id == org_id,
            InspectionFacility.matched_property_id.is_not(None),
        )
    )
    facilities = result.scalars().all()
    logger.info(f"Org {org_id}: {len(facilities)} matched facilities to process")

    totals = {"facilities": len(facilities), "synced": 0, "no_op": 0, "errors": 0,
              "items_created": 0, "items_updated": 0, "items_skipped": 0}
    svc = InspectionService(db)

    for f in facilities:
        try:
            if dry_run:
                logger.info(f"  [dry-run] would sync facility {f.id} ({f.name})")
                continue
            result = await svc.sync_equipment_to_bow(f.id)
            if not result:
                totals["no_op"] += 1
                continue
            totals["synced"] += 1
            items = result.get("updated_fields", {}).get("equipment_items") or {}
            totals["items_created"] += items.get("created", 0)
            totals["items_updated"] += items.get("updated", 0)
            totals["items_skipped"] += items.get("skipped", 0)
            logger.info(f"  facility {f.id} ({f.name}): {items}")
        except Exception as e:  # noqa: BLE001
            totals["errors"] += 1
            logger.exception(f"  facility {f.id} ({f.name}) FAILED: {e}")

    if not dry_run:
        await db.commit()
    return totals


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--org-id", help="UUID of organization to backfill", default=None)
    parser.add_argument("--all-orgs", action="store_true", help="Backfill every org")
    parser.add_argument("--dry-run", action="store_true", help="Don't commit; just report what would happen")
    args = parser.parse_args()

    if not args.org_id and not args.all_orgs:
        parser.error("must pass either --org-id <uuid> or --all-orgs")

    async with get_db_context() as db:
        if args.all_orgs:
            result = await db.execute(select(Organization.id))
            org_ids = [r[0] for r in result.all()]
        else:
            org_ids = [args.org_id]

        grand_total = {"facilities": 0, "synced": 0, "no_op": 0, "errors": 0,
                       "items_created": 0, "items_updated": 0, "items_skipped": 0}
        for oid in org_ids:
            totals = await backfill_one_org(db, oid, dry_run=args.dry_run)
            for k in grand_total:
                grand_total[k] += totals[k]

        logger.info(f"FINAL: {grand_total}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
