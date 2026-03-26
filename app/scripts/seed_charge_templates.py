"""Seed default charge templates for all existing organizations."""

import asyncio
import uuid
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.core.database import get_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

TEMPLATES = [
    {"name": "Debris Cleanup", "default_amount": 45.0, "category": "time", "sort_order": 0},
    {"name": "Extra Chemicals", "default_amount": 25.0, "category": "chemical", "sort_order": 1},
    {"name": "Storm Cleanup", "default_amount": 95.0, "category": "time", "sort_order": 2},
    {"name": "Green Pool Assessment", "default_amount": 150.0, "category": "time", "requires_approval": True, "sort_order": 3},
    {"name": "Minor Repair", "default_amount": 75.0, "category": "material", "sort_order": 4},
    {"name": "Extra Service Time (15 min)", "default_amount": 30.0, "category": "time", "sort_order": 5},
]


async def main():
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as db:
        # Get all org IDs
        result = await db.execute(text("SELECT id, name FROM organizations"))
        orgs = result.fetchall()
        if not orgs:
            print("No organizations found.")
            return

        for org_id, org_name in orgs:
            # Check if templates already exist
            existing = await db.execute(
                text("SELECT COUNT(*) FROM charge_templates WHERE organization_id = :oid"),
                {"oid": org_id},
            )
            count = existing.scalar()
            if count > 0:
                print(f"  Skipping {org_name} — already has {count} templates")
                continue

            now = datetime.now(timezone.utc)
            for tmpl in TEMPLATES:
                await db.execute(
                    text("""
                        INSERT INTO charge_templates (id, organization_id, name, default_amount, category,
                            is_taxable, requires_approval, is_active, sort_order, created_at, updated_at)
                        VALUES (:id, :org_id, :name, :amount, :category, :taxable, :approval, true, :sort, :now, :now)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "org_id": org_id,
                        "name": tmpl["name"],
                        "amount": tmpl["default_amount"],
                        "category": tmpl["category"],
                        "taxable": True,
                        "approval": tmpl.get("requires_approval", False),
                        "sort": tmpl["sort_order"],
                        "now": now,
                    },
                )
            print(f"  Seeded {len(TEMPLATES)} templates for {org_name}")
        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
