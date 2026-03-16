"""Seed regional chemical defaults — Sacramento CA + national fallback."""

import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.regional_default import RegionalDefault

# Sacramento CA defaults and national fallback (same initial values)
DEFAULTS = [
    # Liquid chlorine — most common in Sacramento commercial
    # Typical: 0.75-1.5 gal per 20k pool per visit = ~48-96 oz per 10k gal
    {
        "sanitizer_type": "liquid",
        "sanitizer_usage_oz": 64.0,  # 64 oz (0.5 gal) per 10k gal per visit
        "sanitizer_price_per_unit": 3.50,
        "sanitizer_unit": "gallon",
        "acid_usage_oz": 16.0,  # ~1 cup per 10k gal per visit
        "acid_price_per_gallon": 8.00,
        "cya_price_per_lb": 4.50,
        "salt_price_per_bag": 7.00,
        "cya_usage_lb_per_month_per_10k": 1.0,
        "salt_bags_per_year_per_10k": 2.0,
    },
    # Tabs (trichlor) — common residential
    # ~3 tabs (8oz each) per 10k gal per visit
    {
        "sanitizer_type": "tabs",
        "sanitizer_usage_oz": 24.0,  # ~3 tabs per 10k gal per visit
        "sanitizer_price_per_unit": 85.00,
        "sanitizer_unit": "bucket",  # 50lb bucket (800oz)
        "acid_usage_oz": 12.0,
        "acid_price_per_gallon": 8.00,
        "cya_price_per_lb": 4.50,
        "salt_price_per_bag": 7.00,
        "cya_usage_lb_per_month_per_10k": 1.0,
        "salt_bags_per_year_per_10k": 2.0,
    },
    # Salt (chlorine generator)
    {
        "sanitizer_type": "salt",
        "sanitizer_usage_oz": 0.0,  # cell generates chlorine
        "sanitizer_price_per_unit": 7.00,
        "sanitizer_unit": "bag",  # 40lb bag
        "acid_usage_oz": 20.0,  # salt pools tend to run high pH
        "acid_price_per_gallon": 8.00,
        "cya_price_per_lb": 4.50,
        "salt_price_per_bag": 7.00,
        "cya_usage_lb_per_month_per_10k": 1.0,
        "salt_bags_per_year_per_10k": 2.0,
    },
    # Cal hypo (calcium hypochlorite)
    # ~4-8 oz per 10k gal per visit
    {
        "sanitizer_type": "cal_hypo",
        "sanitizer_usage_oz": 8.0,
        "sanitizer_price_per_unit": 3.25,
        "sanitizer_unit": "lb",
        "acid_usage_oz": 16.0,
        "acid_price_per_gallon": 8.00,
        "cya_price_per_lb": 4.50,
        "salt_price_per_bag": 7.00,
        "cya_usage_lb_per_month_per_10k": 1.0,
        "salt_bags_per_year_per_10k": 2.0,
    },
    # Dichlor
    {
        "sanitizer_type": "dichlor",
        "sanitizer_usage_oz": 4.0,
        "sanitizer_price_per_unit": 5.00,
        "sanitizer_unit": "lb",
        "acid_usage_oz": 12.0,
        "acid_price_per_gallon": 8.00,
        "cya_price_per_lb": 4.50,
        "salt_price_per_bag": 7.00,
        "cya_usage_lb_per_month_per_10k": 1.0,
        "salt_bags_per_year_per_10k": 2.0,
    },
    # Bromine
    {
        "sanitizer_type": "bromine",
        "sanitizer_usage_oz": 8.0,
        "sanitizer_price_per_unit": 6.00,
        "sanitizer_unit": "lb",
        "acid_usage_oz": 8.0,
        "acid_price_per_gallon": 8.00,
        "cya_price_per_lb": 4.50,
        "salt_price_per_bag": 7.00,
        "cya_usage_lb_per_month_per_10k": 1.0,
        "salt_bags_per_year_per_10k": 2.0,
    },
]

REGIONS = ["sacramento_ca", "national"]


async def seed_regional_defaults(db: AsyncSession):
    """Insert regional defaults for Sacramento CA and national fallback."""
    now = datetime.now(timezone.utc)
    created = 0

    for region_key in REGIONS:
        for defaults in DEFAULTS:
            # Check if already exists
            result = await db.execute(
                select(RegionalDefault).where(
                    RegionalDefault.region_key == region_key,
                    RegionalDefault.sanitizer_type == defaults["sanitizer_type"],
                )
            )
            if result.scalar_one_or_none():
                continue

            row = RegionalDefault(
                id=str(uuid.uuid4()),
                region_key=region_key,
                source="verified" if region_key == "sacramento_ca" else "ai_estimated",
                last_updated=now,
                **defaults,
            )
            db.add(row)
            created += 1

    await db.flush()
    return created


async def main():
    async with get_db_context() as db:
        count = await seed_regional_defaults(db)
        print(f"Created {count} regional default records")


if __name__ == "__main__":
    asyncio.run(main())
