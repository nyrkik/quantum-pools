#!/usr/bin/env python
"""One-time fixer: equipment_items rows whose brand contradicts their type.

Targets the bug where the EMD PDF extractor sometimes drops sanitizer-feeder
brands (Rolachem, Stenner, Pulsar, Blue-White, etc.) into `filter_pump_*`
fields — so my v1 sync created `equipment_type='pump'` rows for what are
clearly chemical feeders. Most of these are double-captures of the same
device that the `sanitizer_1_*` slot already represented.

What this does, per row:
  1. Match brand against `brand_authority.authoritative_type()`.
  2. If the row's equipment_type differs from the authority answer:
     - If the same WF already has a row of the authoritative type with the
       same brand, soft-delete the misrouted row (it's a dup).
     - Otherwise, flip the misrouted row's equipment_type in place.
  3. Log a `rejection`/`edit` correction so the equipment_resolver agent
     learns from the fix.

Idempotent. Use `--dry-run` first.

Usage:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python \
      scripts/fix_misclassified_inspection_equipment.py --org-id <uuid>
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python \
      scripts/fix_misclassified_inspection_equipment.py --all-orgs --dry-run
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
from src.services.equipment.brand_authority import authoritative_type

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fix_misclassified_inspection_equipment")


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


async def fix_one_org(db: AsyncSession, org_id: str, dry_run: bool) -> dict:
    totals = {"scanned": 0, "deleted": 0, "type_flipped": 0, "untouched": 0}

    result = await db.execute(
        select(EquipmentItem).where(
            EquipmentItem.organization_id == org_id,
            EquipmentItem.source_inspection_id.is_not(None),
            EquipmentItem.is_active == True,
        )
    )
    items = result.scalars().all()
    totals["scanned"] = len(items)

    # Index by water_feature for fast same-WF lookups
    by_wf: dict[str, list[EquipmentItem]] = {}
    for it in items:
        by_wf.setdefault(it.water_feature_id, []).append(it)

    learner = AgentLearningService(db)

    for it in items:
        auth = authoritative_type(it.brand)
        if not auth or auth == it.equipment_type:
            totals["untouched"] += 1
            continue

        # Same-WF dedup is intentionally narrow: only delete when there's a
        # definite same-entity match (brand OR model overlap) on a row of the
        # authoritative type. Otherwise flip type in place — having two
        # sanitizer rows on a WF is acceptable (they may represent different
        # devices, or be cross-inspection dups that a separate cleanup pass
        # handles). Wrong type in production is worse.
        bn = _norm(it.brand)
        mn = _norm(it.model)
        same_entity_in_auth = None
        for other in by_wf.get(it.water_feature_id, []):
            if other.id == it.id or not other.is_active:
                continue
            if other.equipment_type != auth:
                continue
            other_haystack = " ".join([_norm(other.brand), _norm(other.model), _norm(other.notes)])
            brand_overlap = bn and (bn in other_haystack)
            model_overlap = mn and (mn in other_haystack) and len(mn) >= 4
            if brand_overlap or model_overlap:
                same_entity_in_auth = other
                break

        if same_entity_in_auth:
            # Soft-delete: it's a dup of the sanitizer-slot capture.
            logger.info(
                f"  DELETE dup pump-row {it.id} ({it.brand} / {it.model}) on wf={it.water_feature_id} "
                f"— sanitizer row {same_entity_in_auth.id} already represents it"
            )
            if not dry_run:
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
                        f"PDF extractor double-captured sanitizer brand into "
                        f"slot={it.source_slot}. Authoritative type for brand "
                        f"'{it.brand}' is '{auth}'. Sanitizer row already exists."
                    ),
                    category=auth,
                    source_id=it.id,
                    source_type="equipment_item",
                )
            totals["deleted"] += 1
        else:
            # No competing sanitizer row — flip type in place.
            logger.info(
                f"  FLIP type pump→{auth} for {it.id} ({it.brand} / {it.model}) on wf={it.water_feature_id}"
            )
            if not dry_run:
                pre = {"equipment_type": it.equipment_type, "system_group": it.system_group}
                it.equipment_type = auth
                it.system_group = None
                post = {"equipment_type": it.equipment_type, "system_group": it.system_group}
                await learner.record_correction(
                    org_id=org_id,
                    agent_type=AGENT_EQUIPMENT_RESOLVER,
                    correction_type="edit",
                    original_output=json.dumps(pre, default=str),
                    corrected_output=json.dumps(post, default=str),
                    input_context=(
                        f"Brand '{it.brand}' is authoritatively '{auth}', not 'pump'."
                    ),
                    category=auth,
                    source_id=it.id,
                    source_type="equipment_item",
                )
            totals["type_flipped"] += 1

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
        parser.error("must pass either --org-id <uuid> or --all-orgs")

    async with get_db_context() as db:
        if args.all_orgs:
            result = await db.execute(select(Organization.id))
            org_ids = [r[0] for r in result.all()]
        else:
            org_ids = [args.org_id]

        grand = {"scanned": 0, "deleted": 0, "type_flipped": 0, "untouched": 0}
        for oid in org_ids:
            totals = await fix_one_org(db, oid, dry_run=args.dry_run)
            for k in grand:
                grand[k] += totals[k]
            logger.info(f"Org {oid}: {totals}")
        logger.info(f"FINAL: {grand}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
