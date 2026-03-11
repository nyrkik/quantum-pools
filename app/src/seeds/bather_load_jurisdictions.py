"""Seed bather load jurisdictions — 10 US calculation methods."""

import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.bather_load_jurisdiction import BatherLoadJurisdiction, JurisdictionMethod

JURISDICTIONS = [
    {
        "name": "California",
        "method_key": JurisdictionMethod.california,
        "shallow_sqft_per_bather": 20.0,
        "deep_sqft_per_bather": 20.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": False,
        "depth_break_ft": 5.0,
        "notes": "Flat rate — simplest calculation. 1 bather per 20 sqft regardless of depth.",
    },
    {
        "name": "ISPSC (International)",
        "method_key": JurisdictionMethod.ispsc,
        "shallow_sqft_per_bather": 20.0,
        "deep_sqft_per_bather": 25.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": True,
        "deck_sqft_per_bather": 50.0,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "Depth-based with deck bonus: +1 bather per 50 sqft of excess deck area.",
    },
    {
        "name": "MAHC/CDC",
        "method_key": JurisdictionMethod.mahc,
        "shallow_sqft_per_bather": 20.0,
        "deep_sqft_per_bather": 20.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": True,
        "indoor_multiplier": 1.15,
        "has_limited_use_multiplier": True,
        "limited_use_multiplier": 1.33,
        "depth_based": False,
        "depth_break_ft": 5.0,
        "notes": "Volume formula with indoor (1.15x) and limited-use (1.33x) multipliers.",
    },
    {
        "name": "Texas",
        "method_key": JurisdictionMethod.texas,
        "shallow_sqft_per_bather": 15.0,
        "deep_sqft_per_bather": 20.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "Variable via chart. More permissive shallow allocation than ISPSC.",
    },
    {
        "name": "Florida",
        "method_key": JurisdictionMethod.florida,
        "shallow_sqft_per_bather": 20.0,
        "deep_sqft_per_bather": 20.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": True,
        "flow_gpm_per_bather": 5.0,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": False,
        "depth_break_ft": 5.0,
        "notes": "Dual test: area-based AND 1 per 5 GPM — lesser value wins.",
    },
    {
        "name": "Arizona (Maricopa)",
        "method_key": JurisdictionMethod.arizona,
        "shallow_sqft_per_bather": 10.0,
        "deep_sqft_per_bather": 24.0,
        "spa_sqft_per_bather": 9.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "Swimmer vs non-swimmer zones. Most permissive shallow allocation (10 sqft).",
    },
    {
        "name": "New York",
        "method_key": JurisdictionMethod.new_york,
        "shallow_sqft_per_bather": 15.0,
        "deep_sqft_per_bather": 25.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "Staffing rules apply at 3400+ sqft. Depth-based like ISPSC with tighter shallow.",
    },
    {
        "name": "Georgia",
        "method_key": JurisdictionMethod.georgia,
        "shallow_sqft_per_bather": 18.0,
        "deep_sqft_per_bather": 20.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "ISPSC with amendments. Slightly tighter shallow allocation.",
    },
    {
        "name": "North Carolina",
        "method_key": JurisdictionMethod.north_carolina,
        "shallow_sqft_per_bather": 15.0,
        "deep_sqft_per_bather": 24.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "Depth-based calculation.",
    },
    {
        "name": "Illinois",
        "method_key": JurisdictionMethod.illinois,
        "shallow_sqft_per_bather": 15.0,
        "deep_sqft_per_bather": 25.0,
        "spa_sqft_per_bather": 10.0,
        "diving_sqft_per_board": 300.0,
        "has_deck_bonus": False,
        "has_flow_rate_test": False,
        "has_indoor_multiplier": False,
        "has_limited_use_multiplier": False,
        "depth_based": True,
        "depth_break_ft": 5.0,
        "notes": "Depth-based calculation.",
    },
]


async def seed_jurisdictions():
    """Insert bather load jurisdictions if they don't exist."""
    async with get_db_context() as db:
        result = await db.execute(select(BatherLoadJurisdiction).limit(1))
        if result.scalar_one_or_none():
            print("Bather load jurisdictions already seeded.")
            return

        for j in JURISDICTIONS:
            db.add(BatherLoadJurisdiction(id=str(uuid.uuid4()), **j))
        await db.flush()
        print(f"Seeded {len(JURISDICTIONS)} bather load jurisdictions.")


if __name__ == "__main__":
    asyncio.run(seed_jurisdictions())
