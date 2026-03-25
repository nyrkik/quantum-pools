"""Difficulty scoring service — weights, range constants, composite score computation."""

import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.property_difficulty import PropertyDifficulty
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.schemas.profitability import PropertyDifficultyResponse


# Difficulty score weights
WEIGHTS = {
    "pool_gallons": 0.10,
    "pool_sqft": 0.05,
    "water_features": 0.08,
    "equipment_effectiveness": 0.07,
    "pool_design": 0.05,
    "shade_debris": 0.05,
    "enclosure": 0.05,
    "chemical_demand": 0.12,
    "service_time": 0.18,
    "distance": 0.10,
    "access": 0.08,
    "customer_demands": 0.07,
}

# Gallon ranges → score 1-5
GALLON_RANGES = [(10000, 1), (20000, 2), (30000, 3), (40000, 4)]
SQFT_RANGES = [(400, 1), (700, 2), (1000, 3), (1500, 4)]
SERVICE_TIME_RANGES = [(20, 1), (30, 2), (45, 3), (60, 4)]


def _range_score(value: Optional[float], ranges: list[tuple]) -> float:
    if value is None:
        return 1.0
    for threshold, score in ranges:
        if value <= threshold:
            return float(score)
    return 5.0


def _shade_score(shade: Optional[str]) -> float:
    return {"full_sun": 1.0, "partial_shade": 3.0, "full_shade": 5.0}.get(shade or "", 1.0)


def _debris_score(debris: Optional[str]) -> float:
    return {"none": 1.0, "low": 2.0, "moderate": 3.5, "heavy": 5.0}.get(debris or "", 1.0)


def _enclosure_score(enclosure: Optional[str]) -> float:
    return {"indoor": 1.0, "screened": 2.0, "open": 3.5}.get(enclosure or "", 3.5)


class DifficultyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_difficulty(self, org_id: str, property_id: str) -> PropertyDifficulty:
        result = await self.db.execute(
            select(PropertyDifficulty).where(
                PropertyDifficulty.property_id == property_id,
                PropertyDifficulty.organization_id == org_id,
            )
        )
        diff = result.scalar_one_or_none()
        if not diff:
            diff = PropertyDifficulty(
                id=str(uuid.uuid4()),
                property_id=property_id,
                organization_id=org_id,
            )
            self.db.add(diff)
            await self.db.flush()
            await self.db.refresh(diff)
        return diff

    async def update_difficulty(self, org_id: str, property_id: str, **kwargs) -> PropertyDifficulty:
        diff = await self.get_or_create_difficulty(org_id, property_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(diff, key, value)
        await self.db.flush()
        await self.db.refresh(diff)
        return diff

    def compute_composite_score(
        self, prop: Property, diff: Optional[PropertyDifficulty],
        wfs: Optional[list[WaterFeature]] = None,
    ) -> float:
        if diff and diff.override_composite is not None:
            return diff.override_composite

        scores = {}

        # Aggregate from WFs if available, else fall back to property fields
        if wfs:
            total_gallons = sum(b.pool_gallons or 0 for b in wfs) or None
            total_sqft = sum(b.pool_sqft or 0 for b in wfs) or None
            total_service_minutes = sum(b.estimated_service_minutes or 0 for b in wfs) or None
            has_spa = any(b.water_type == "spa" for b in wfs)
            has_water_feature = any(b.water_type in ("water_feature", "fountain") for b in wfs)
        else:
            total_gallons = prop.pool_gallons
            total_sqft = prop.pool_sqft
            total_service_minutes = prop.estimated_service_minutes
            has_spa = prop.has_spa
            has_water_feature = prop.has_water_feature

        # Measured factors
        scores["pool_gallons"] = _range_score(total_gallons, GALLON_RANGES)
        scores["pool_sqft"] = _range_score(total_sqft, SQFT_RANGES)
        scores["service_time"] = _range_score(total_service_minutes, SERVICE_TIME_RANGES)

        water_feature_score = 1.0
        if has_spa:
            water_feature_score += 1.5
        if has_water_feature:
            water_feature_score += 1.0
        scores["water_features"] = min(water_feature_score, 5.0)

        # WF-level scores — average across WFs (these live on the WF now)
        if wfs:
            avg = lambda attr, default: sum(getattr(b, attr, default) for b in wfs) / len(wfs)
            scores["equipment_effectiveness"] = 6.0 - avg("equipment_effectiveness", 3.0)
            scores["pool_design"] = 6.0 - avg("pool_design", 3.0)
            scores["chemical_demand"] = avg("chemical_demand", 1.0)
            scores["access"] = avg("access_difficulty", 1.0)
            scores["shade_debris"] = (avg("shade_exposure", 1.0) + avg("tree_debris", 1.0)) / 2.0
        else:
            scores["equipment_effectiveness"] = 3.0
            scores["pool_design"] = 3.0
            scores["chemical_demand"] = 1.0
            scores["access"] = 1.0
            scores["shade_debris"] = 1.0

        # Property-level scores — from PropertyDifficulty
        if diff:
            scores["enclosure"] = _enclosure_score(
                diff.enclosure_type.value if diff.enclosure_type else None
            )
            scores["customer_demands"] = diff.customer_demands_score
        else:
            scores["enclosure"] = 3.5
            scores["customer_demands"] = 1.0

        # Distance — would need route data, default to 1.0
        scores["distance"] = 1.0

        composite = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
        return round(min(max(composite, 1.0), 5.0), 2)

    def difficulty_to_multiplier(self, score: float) -> float:
        return round(0.8 + (score - 1.0) * 0.2, 3)

    def get_difficulty_response(
        self, prop: Property, diff: PropertyDifficulty
    ) -> PropertyDifficultyResponse:
        score = self.compute_composite_score(prop, diff)
        multiplier = self.difficulty_to_multiplier(score)
        resp = PropertyDifficultyResponse.model_validate(diff)
        resp.composite_score = score
        resp.difficulty_multiplier = multiplier
        return resp
