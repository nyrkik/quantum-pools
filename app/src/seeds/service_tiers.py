"""Seed default service tiers for existing organizations."""

import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.service_tier import ServiceTier
from src.models.organization import Organization

DEFAULT_TIERS = [
    {
        "name": "Silver",
        "slug": "silver",
        "description": "Chemical service only — test and adjust water chemistry.",
        "sort_order": 0,
        "base_rate": 129.0,
        "estimated_minutes": 10,
        "includes_chems": True,
        "includes_skim": False,
        "includes_baskets": False,
        "includes_vacuum": False,
        "includes_brush": False,
        "includes_equipment_check": False,
        "is_default": True,
    },
    {
        "name": "Silver Plus",
        "slug": "silver_plus",
        "description": "Chemicals, skim surface, empty baskets, equipment check.",
        "sort_order": 10,
        "base_rate": 169.0,
        "estimated_minutes": 20,
        "includes_chems": True,
        "includes_skim": True,
        "includes_baskets": True,
        "includes_vacuum": False,
        "includes_brush": False,
        "includes_equipment_check": True,
        "is_default": False,
    },
    {
        "name": "Gold",
        "slug": "gold",
        "description": "Full service — chemicals, skim, baskets, vacuum, equipment check.",
        "sort_order": 20,
        "base_rate": 189.0,
        "estimated_minutes": 35,
        "includes_chems": True,
        "includes_skim": True,
        "includes_baskets": True,
        "includes_vacuum": True,
        "includes_brush": False,
        "includes_equipment_check": True,
        "is_default": False,
    },
]


async def seed_service_tiers():
    """Create default service tiers for all orgs that don't have any."""
    async with get_db_context() as db:
        result = await db.execute(select(Organization))
        orgs = result.scalars().all()

        for org in orgs:
            existing = await db.execute(
                select(ServiceTier).where(ServiceTier.organization_id == org.id).limit(1)
            )
            if existing.scalar_one_or_none():
                print(f"  {org.name}: already has tiers")
                continue

            for t in DEFAULT_TIERS:
                db.add(ServiceTier(id=str(uuid.uuid4()), organization_id=org.id, **t))

            await db.flush()
            print(f"  {org.name}: seeded {len(DEFAULT_TIERS)} tiers")


if __name__ == "__main__":
    asyncio.run(seed_service_tiers())
