#!/usr/bin/env python
"""Dedup equipment_items rows that represent the same physical equipment but
were imported from multiple inspections of the same property.

Each annual inspection creates its own InspectionEquipment row → my v1 sync
keys dedup on (wf_id, source_inspection_id, source_slot), so a 2024 + 2025
inspection of the same property both produce a Pentair Whisperflo row and
they coexist as two active rows. Bug: the property profile shows duplicate
equipment.

Rule for dedup: within the same WF, group rows by exact match on
(LOWER(brand), LOWER(model), equipment_type, system_group, horsepower).
For groups with >1 row, keep the row sourced from the most recent inspection
(by Inspection.inspection_date DESC, falling back to created_at DESC) and
soft-delete the rest. Manual rows (source_inspection_id IS NULL) are
authoritative — never touched.

Usage:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python \
      scripts/dedup_cross_inspection_equipment.py --org-id <uuid> [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.equipment_item import EquipmentItem
from src.models.inspection import Inspection
from src.models.organization import Organization
from src.services.agent_learning_service import (
    AGENT_EQUIPMENT_RESOLVER,
    AgentLearningService,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dedup_cross_inspection_equipment")


def _norm(s) -> str:
    return (s or "").strip().lower() if isinstance(s, str) else ""


async def fix_one_org(db: AsyncSession, org_id: str, dry_run: bool) -> dict:
    totals = {"groups_examined": 0, "groups_with_dups": 0, "rows_kept": 0, "rows_soft_deleted": 0}

    # Fetch all active inspection-sourced rows + their inspection_date
    result = await db.execute(
        select(EquipmentItem, Inspection.inspection_date)
        .join(Inspection, Inspection.id == EquipmentItem.source_inspection_id, isouter=True)
        .where(
            EquipmentItem.organization_id == org_id,
            EquipmentItem.source_inspection_id.is_not(None),
            EquipmentItem.is_active == True,
        )
    )
    rows: list[tuple[EquipmentItem, object]] = result.all()

    # Group by (wf_id, type, group, brand, model, hp) — exact match
    groups: dict[tuple, list[tuple[EquipmentItem, object]]] = defaultdict(list)
    for it, insp_date in rows:
        # Skip rows missing brand AND model — too ambiguous to dedup
        if not (it.brand or it.model):
            continue
        key = (
            it.water_feature_id,
            it.equipment_type or "",
            it.system_group or "",
            _norm(it.brand),
            _norm(it.model),
            float(it.horsepower) if it.horsepower is not None else None,
        )
        groups[key].append((it, insp_date))

    totals["groups_examined"] = len(groups)
    learner = AgentLearningService(db)

    for key, members in groups.items():
        if len(members) < 2:
            continue
        totals["groups_with_dups"] += 1

        # Sort newest-first: inspection_date DESC nulls last, then created_at DESC
        members.sort(
            key=lambda m: (m[1] is None, -(m[1].toordinal() if m[1] else 0), -m[0].created_at.timestamp()),
        )
        keep = members[0][0]
        kill = [m[0] for m in members[1:]]

        wf_id, etype, sgroup, brand, model, hp = key
        logger.info(
            f"  GROUP wf={wf_id} type={etype} group={sgroup or '—'} brand={brand} model={model} hp={hp}"
        )
        logger.info(f"    KEEP   {keep.id} (slot={keep.source_slot} inspection={keep.source_inspection_id})")
        for it in kill:
            logger.info(f"    DELETE {it.id} (slot={it.source_slot} inspection={it.source_inspection_id})")

        if not dry_run:
            for it in kill:
                pre = {
                    "equipment_type": it.equipment_type, "brand": it.brand,
                    "model": it.model, "source_slot": it.source_slot,
                }
                it.is_active = False
                await learner.record_correction(
                    org_id=org_id,
                    agent_type=AGENT_EQUIPMENT_RESOLVER,
                    correction_type="rejection",
                    original_output=json.dumps(pre, default=str),
                    input_context=(
                        f"Cross-inspection duplicate. Same physical equipment "
                        f"already represented by {keep.id} (newer inspection). "
                        f"Soft-deleted to preserve audit trail."
                    ),
                    category=etype,
                    source_id=it.id,
                    source_type="equipment_item",
                )

        totals["rows_kept"] += 1
        totals["rows_soft_deleted"] += len(kill)

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

        grand = {"groups_examined": 0, "groups_with_dups": 0, "rows_kept": 0, "rows_soft_deleted": 0}
        for oid in org_ids:
            totals = await fix_one_org(db, oid, dry_run=args.dry_run)
            for k in grand:
                grand[k] += totals[k]
            logger.info(f"Org {oid}: {totals}")
        logger.info(f"FINAL: {grand}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
