"""Backfill equipment normalization — reads all water_features with equipment data,
normalizes each, and creates equipment_items with structured fields.

Usage:
    cd /srv/quantumpools/app
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python -m scripts.normalize_equipment
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add app root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("normalize_equipment")

FIELD_TO_TYPE = {
    "pump_type": "pump",
    "filter_type": "filter",
    "heater_type": "heater",
    "chlorinator_type": "chlorinator",
    "automation_system": "automation",
}


async def main():
    from sqlalchemy import select
    from src.core.database import get_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.models.water_feature import WaterFeature
    from src.services.parts.equipment_normalizer import EquipmentNormalizer

    engine = get_engine()
    async with AsyncSession(engine) as db:
        # Get all water features with any equipment data
        result = await db.execute(select(WaterFeature))
        water_features = result.scalars().all()

        total = 0
        created = 0
        skipped = 0
        errors = 0

        for wf in water_features:
            normalizer = EquipmentNormalizer(db)

            for field, eq_type in FIELD_TO_TYPE.items():
                raw = getattr(wf, field, None)
                if not raw or not raw.strip():
                    continue

                total += 1
                raw = raw.strip()

                try:
                    normalized = await normalizer.normalize(raw, eq_type)
                    item = await normalizer.upsert_equipment_item(
                        wf.organization_id, wf.id, eq_type, raw, normalized
                    )
                    if item:
                        created += 1
                        logger.info(
                            f"  {eq_type}: '{raw}' -> '{normalized.get('normalized_name', 'N/A')}'"
                        )
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"  Failed {eq_type} for WF {wf.id}: {e}")

        await db.commit()

    logger.info(f"Done. Total: {total}, Created/Updated: {created}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
