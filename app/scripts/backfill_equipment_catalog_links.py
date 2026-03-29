"""Backfill equipment_items.catalog_equipment_id from catalog aliases.

Run: /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_equipment_catalog_links.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func, cast, String
from src.core.database import get_db_context
from src.models.equipment_item import EquipmentItem
from src.models.equipment_catalog import EquipmentCatalog


async def backfill():
    async with get_db_context() as db:
        # Load all catalog entries
        catalog_result = await db.execute(
            select(EquipmentCatalog).where(EquipmentCatalog.is_active == True)
        )
        catalog_entries = catalog_result.scalars().all()

        # Build alias lookup: lowercase alias → catalog entry
        alias_map: dict[str, EquipmentCatalog] = {}
        for entry in catalog_entries:
            for alias in (entry.aliases or []):
                alias_map[alias.strip().lower()] = entry
            # Also index by canonical_name and model_number
            alias_map[entry.canonical_name.lower()] = entry
            if entry.model_number and entry.model_number != "?":
                alias_map[entry.model_number.lower()] = entry

        # Get all unlinked equipment items
        items_result = await db.execute(
            select(EquipmentItem).where(
                EquipmentItem.is_active == True,
                EquipmentItem.catalog_equipment_id.is_(None),
            )
        )
        items = items_result.scalars().all()

        matched = 0
        unmatched = []

        for item in items:
            # Try various search strings
            search_strings = []
            if item.model:
                search_strings.append(item.model.strip().lower())
            if item.brand and item.model:
                search_strings.append(f"{item.brand.strip()} {item.model.strip()}".lower())
            if item.normalized_name:
                search_strings.append(item.normalized_name.strip().lower())

            found = None
            for s in search_strings:
                if s in alias_map:
                    found = alias_map[s]
                    break
                # Try partial match — check if any alias is contained in the search string or vice versa
                for alias, entry in alias_map.items():
                    if len(alias) >= 4 and (alias in s or s in alias):
                        found = entry
                        break
                if found:
                    break

            if found:
                item.catalog_equipment_id = found.id
                matched += 1
            else:
                name = item.normalized_name or f"{item.brand or ''} {item.model or ''}".strip()
                if name.strip():
                    unmatched.append(f"  {item.equipment_type:20s} | {name}")

        await db.commit()

        print(f"\nBackfill Results:")
        print(f"  Matched: {matched}")
        print(f"  Unmatched: {len(unmatched)}")
        print(f"  Total: {len(items)}")

        if unmatched:
            print(f"\nUnmatched equipment ({len(unmatched)}):")
            # Deduplicate for readability
            seen = set()
            for u in sorted(set(unmatched)):
                print(u)


if __name__ == "__main__":
    asyncio.run(backfill())
