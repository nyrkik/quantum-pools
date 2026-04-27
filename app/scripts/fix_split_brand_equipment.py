#!/usr/bin/env python
"""Fixer: equipment_items rows whose brand was split mid-word by the PDF extractor.

Symptoms:
  brand='P' model='urex Triton CC'  → Purex Triton CC
  brand='H' model='ayward C-'       → Hayward C-

Walks every active inspection-sourced equipment_items row, calls
`brand_reassembler.reassemble(brand, model)`. If it returns a corrected
(brand, model) tuple, updates the row in place and logs an `edit` correction.

Idempotent. Use --dry-run first.

Usage:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python \
      scripts/fix_split_brand_equipment.py --org-id <uuid> [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.equipment_item import EquipmentItem
from src.models.organization import Organization
from src.services.agent_learning_service import (
    AGENT_EQUIPMENT_RESOLVER,
    AgentLearningService,
)
from src.services.equipment.brand_reassembler import reassemble

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fix_split_brand_equipment")


async def fix_one_org(db: AsyncSession, org_id: str, dry_run: bool) -> dict:
    totals = {"scanned": 0, "fixed": 0}

    result = await db.execute(
        select(EquipmentItem).where(
            EquipmentItem.organization_id == org_id,
            EquipmentItem.source_inspection_id.is_not(None),
            EquipmentItem.is_active == True,
        )
    )
    items = result.scalars().all()
    totals["scanned"] = len(items)

    learner = AgentLearningService(db)
    for it in items:
        fixed = reassemble(it.brand, it.model)
        if fixed is None:
            continue
        new_brand, new_model = fixed
        if new_brand == it.brand and new_model == it.model:
            continue

        logger.info(
            f"  FIX {it.id}  brand='{it.brand}' model='{it.model}'  →  brand='{new_brand}' model='{new_model}'"
        )
        if not dry_run:
            pre = {"brand": it.brand, "model": it.model}
            it.brand = new_brand
            it.model = new_model
            it.normalized_name = " ".join(filter(None, [new_brand, new_model])) or None
            await learner.record_correction(
                org_id=org_id,
                agent_type=AGENT_EQUIPMENT_RESOLVER,
                correction_type="edit",
                original_output=json.dumps(pre, default=str),
                corrected_output=json.dumps({"brand": new_brand, "model": new_model}, default=str),
                input_context=(
                    f"PDF extractor split brand mid-word; reassembled "
                    f"'{pre['brand']}' + '{pre['model']}' = '{new_brand} {new_model}'."
                ),
                category=it.equipment_type,
                source_id=it.id,
                source_type="equipment_item",
            )
        totals["fixed"] += 1

    if not dry_run:
        await db.commit()
    return totals


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--org-id", default=None)
    parser.add_argument("--all-orgs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.org_id and not args.all_orgs:
        parser.error("must pass --org-id <uuid> or --all-orgs")

    async with get_db_context() as db:
        if args.all_orgs:
            result = await db.execute(select(Organization.id))
            org_ids = [r[0] for r in result.all()]
        else:
            org_ids = [args.org_id]

        grand = {"scanned": 0, "fixed": 0}
        for oid in org_ids:
            totals = await fix_one_org(db, oid, dry_run=args.dry_run)
            for k in grand:
                grand[k] += totals[k]
            logger.info(f"Org {oid}: {totals}")
        logger.info(f"FINAL: {grand}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
