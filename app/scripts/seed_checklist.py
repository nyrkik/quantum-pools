"""Seed default service checklist items for all orgs."""

import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from src.core.database import get_engine

ORG_IDS = [
    "7ef7ab72-703f-45c1-847f-565101cb3e61",  # Sapphire
    "28bcb1c5-91a5-4af8-a2fe-0fe7fe4fc3b5",  # Test Pool Co
]

ITEMS = [
    # Cleaning
    {"name": "Skim surface", "category": "cleaning", "sort_order": 1},
    {"name": "Empty skimmer baskets", "category": "cleaning", "sort_order": 2},
    {"name": "Empty pump basket", "category": "cleaning", "sort_order": 3},
    {"name": "Brush walls & tile", "category": "cleaning", "sort_order": 4},
    {"name": "Vacuum pool", "category": "cleaning", "sort_order": 5},
    # Equipment
    {"name": "Backwash filter", "category": "equipment", "sort_order": 6},
    {"name": "Check pump & motor", "category": "equipment", "sort_order": 7},
    {"name": "Check chlorinator/feeder", "category": "equipment", "sort_order": 8},
    # Chemical
    {"name": "Test water chemistry", "category": "chemical", "sort_order": 9},
    {"name": "Add chemicals as needed", "category": "chemical", "sort_order": 10},
    # Safety
    {"name": "Check water level", "category": "safety", "sort_order": 11},
    {"name": "Inspect drain covers", "category": "safety", "sort_order": 12},
]


async def seed():
    engine = get_engine()
    async with engine.begin() as conn:
        # Check if already seeded
        result = await conn.execute(text("SELECT count(*) FROM service_checklist_items"))
        count = result.scalar()
        if count > 0:
            print(f"Already seeded ({count} items). Skipping.")
            return

        now = datetime.now(timezone.utc)
        for org_id in ORG_IDS:
            for item in ITEMS:
                await conn.execute(
                    text(
                        "INSERT INTO service_checklist_items "
                        "(id, organization_id, name, category, sort_order, applies_to, is_default, is_active, created_at) "
                        "VALUES (:id, :org_id, :name, :category, :sort_order, 'all', true, true, :created_at)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org_id": org_id,
                        "name": item["name"],
                        "category": item["category"],
                        "sort_order": item["sort_order"],
                        "created_at": now,
                    },
                )
            print(f"Seeded 12 checklist items for org {org_id}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
