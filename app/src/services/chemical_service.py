"""Chemical reading service — record readings and generate dosing recommendations."""

import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.chemical_reading import ChemicalReading
from src.models.property import Property
from src.core.exceptions import NotFoundError


# Ideal ranges for pool chemistry
IDEAL_RANGES = {
    "ph": {"min": 7.2, "max": 7.6, "unit": ""},
    "free_chlorine": {"min": 1.0, "max": 3.0, "unit": "ppm"},
    "total_chlorine": {"min": 1.0, "max": 3.0, "unit": "ppm"},
    "alkalinity": {"min": 80, "max": 120, "unit": "ppm"},
    "calcium_hardness": {"min": 200, "max": 400, "unit": "ppm"},
    "cyanuric_acid": {"min": 30, "max": 50, "unit": "ppm"},
    "phosphates": {"min": 0, "max": 300, "unit": "ppb"},
    "salt": {"min": 2700, "max": 3400, "unit": "ppm"},
}


class ChemicalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_property(
        self, org_id: str, property_id: str, limit: int = 50
    ) -> List[ChemicalReading]:
        result = await self.db.execute(
            select(ChemicalReading)
            .where(
                ChemicalReading.organization_id == org_id,
                ChemicalReading.property_id == property_id,
            )
            .order_by(ChemicalReading.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, reading_id: str) -> ChemicalReading:
        result = await self.db.execute(
            select(ChemicalReading).where(
                ChemicalReading.id == reading_id,
                ChemicalReading.organization_id == org_id,
            )
        )
        reading = result.scalar_one_or_none()
        if not reading:
            raise NotFoundError("Chemical reading not found")
        return reading

    async def create(self, org_id: str, pool_gallons: Optional[int] = None, **kwargs) -> ChemicalReading:
        reading = ChemicalReading(id=str(uuid.uuid4()), organization_id=org_id, **kwargs)

        # Auto-fetch pool_gallons if not provided
        if pool_gallons is None:
            prop_result = await self.db.execute(
                select(Property).where(Property.id == kwargs.get("property_id"))
            )
            prop = prop_result.scalar_one_or_none()
            if prop:
                pool_gallons = prop.pool_gallons

        # Generate recommendations
        reading.recommendations = self.generate_recommendations(reading, pool_gallons)

        self.db.add(reading)
        await self.db.flush()
        await self.db.refresh(reading)
        return reading

    @staticmethod
    def generate_recommendations(
        reading: ChemicalReading, pool_gallons: Optional[int] = None
    ) -> dict:
        recs = {"issues": [], "actions": []}
        gallons = pool_gallons or 15000  # Default assumption

        # pH
        if reading.ph is not None:
            if reading.ph < 7.2:
                diff = 7.4 - reading.ph
                soda_ash_oz = diff * gallons / 10000 * 6
                recs["issues"].append(f"pH low ({reading.ph})")
                recs["actions"].append(f"Add {soda_ash_oz:.1f} oz soda ash to raise pH")
            elif reading.ph > 7.6:
                diff = reading.ph - 7.4
                acid_oz = diff * gallons / 10000 * 16
                recs["issues"].append(f"pH high ({reading.ph})")
                recs["actions"].append(f"Add {acid_oz:.1f} oz muriatic acid to lower pH")

        # Free chlorine
        if reading.free_chlorine is not None:
            if reading.free_chlorine < 1.0:
                diff = 2.0 - reading.free_chlorine
                chlorine_oz = diff * gallons / 10000 * 13
                recs["issues"].append(f"Free chlorine low ({reading.free_chlorine} ppm)")
                recs["actions"].append(f"Add {chlorine_oz:.1f} oz liquid chlorine")
            elif reading.free_chlorine > 5.0:
                recs["issues"].append(f"Free chlorine high ({reading.free_chlorine} ppm)")
                recs["actions"].append("Reduce chlorine output or wait for levels to drop")

        # Combined chlorine (chloramines)
        if reading.combined_chlorine is not None and reading.combined_chlorine > 0.5:
            shock_lbs = gallons / 10000
            recs["issues"].append(f"Combined chlorine high ({reading.combined_chlorine} ppm)")
            recs["actions"].append(f"Shock with {shock_lbs:.1f} lbs calcium hypochlorite")

        # Alkalinity
        if reading.alkalinity is not None:
            if reading.alkalinity < 80:
                diff = 100 - reading.alkalinity
                baking_soda_lbs = diff * gallons / 10000 * 0.13
                recs["issues"].append(f"Alkalinity low ({reading.alkalinity} ppm)")
                recs["actions"].append(f"Add {baking_soda_lbs:.1f} lbs baking soda")
            elif reading.alkalinity > 120:
                recs["issues"].append(f"Alkalinity high ({reading.alkalinity} ppm)")
                recs["actions"].append("Add muriatic acid to lower alkalinity (will also lower pH)")

        # Calcium hardness
        if reading.calcium_hardness is not None:
            if reading.calcium_hardness < 200:
                diff = 300 - reading.calcium_hardness
                calcium_lbs = diff * gallons / 10000 * 0.09
                recs["issues"].append(f"Calcium hardness low ({reading.calcium_hardness} ppm)")
                recs["actions"].append(f"Add {calcium_lbs:.1f} lbs calcium chloride")
            elif reading.calcium_hardness > 400:
                recs["issues"].append(f"Calcium hardness high ({reading.calcium_hardness} ppm)")
                recs["actions"].append("Partially drain and refill to dilute")

        # CYA
        if reading.cyanuric_acid is not None:
            if reading.cyanuric_acid < 30:
                diff = 40 - reading.cyanuric_acid
                cya_lbs = diff * gallons / 10000 * 0.13
                recs["issues"].append(f"CYA low ({reading.cyanuric_acid} ppm)")
                recs["actions"].append(f"Add {cya_lbs:.1f} lbs stabilizer (cyanuric acid)")
            elif reading.cyanuric_acid > 80:
                recs["issues"].append(f"CYA high ({reading.cyanuric_acid} ppm)")
                recs["actions"].append("Partially drain and refill to dilute CYA")

        # Phosphates
        if reading.phosphates is not None and reading.phosphates > 300:
            recs["issues"].append(f"Phosphates high ({reading.phosphates} ppb)")
            recs["actions"].append("Add phosphate remover per product instructions")

        if not recs["issues"]:
            recs["issues"].append("All readings within normal range")

        return recs
