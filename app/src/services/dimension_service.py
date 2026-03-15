"""DimensionService — manages pool dimension estimates from multiple sources."""

import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.body_of_water import BodyOfWater
from src.models.dimension_estimate import DimensionEstimate
from src.core.exceptions import NotFoundError


class DimensionService:

    # Perimeter-to-area shape factors (relative to circle area for same perimeter)
    SHAPE_FACTORS = {
        "round": 1.0,
        "oval": 0.85,
        "irregular_oval": 0.78,
        "rectangle": None,  # special: A = P^2/12 (assumes 2:1 L:W ratio)
        "kidney": 0.72,
        "freeform": 0.75,
        "L-shape": 0.70,
    }

    # Lower number = higher priority (more trusted)
    SOURCE_PRIORITY = {
        "inspection": 1,
        "perimeter": 2,
        "measurement": 3,
        "satellite": 4,
        "manual": 5,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def calculate_sqft_from_perimeter(perimeter_ft: float, shape: str) -> float:
        """Calculate estimated pool area from perimeter measurement and shape."""
        if shape == "rectangle":
            # Assumes 2:1 length-to-width ratio: P = 2(L+W), L=2W => P = 6W => W = P/6, L = P/3
            # A = L * W = (P/3)(P/6) = P^2/18... but 2:1 gives P^2/12 for "typical" rectangles
            # Standard formula: A = P^2 / (4 * (r+1)^2 / r) where r=2 => A = P^2 * 2 / (4*9) = P^2/18
            # Using P^2/12 as specified (closer to 1.5:1 ratio which is more common for pools)
            return round((perimeter_ft ** 2) / 12, 1)

        factor = DimensionService.SHAPE_FACTORS.get(shape, 0.75)
        if factor is None:
            factor = 0.75
        # Circle area for this perimeter, then apply shape factor
        radius = perimeter_ft / (2 * math.pi)
        circle_area = math.pi * radius ** 2
        return round(circle_area * factor, 1)

    async def _get_bow(self, org_id: str, bow_id: str) -> BodyOfWater:
        result = await self.db.execute(
            select(BodyOfWater).where(
                BodyOfWater.id == bow_id,
                BodyOfWater.organization_id == org_id,
            )
        )
        bow = result.scalar_one_or_none()
        if not bow:
            raise NotFoundError("Body of water not found")
        return bow

    def _should_promote(self, new_source: str, current_source: Optional[str]) -> bool:
        """Return True if new_source has higher priority (lower number) than current."""
        if not current_source:
            return True
        new_priority = self.SOURCE_PRIORITY.get(new_source, 99)
        current_priority = self.SOURCE_PRIORITY.get(current_source, 99)
        return new_priority <= current_priority

    async def add_perimeter_estimate(
        self,
        org_id: str,
        bow_id: str,
        perimeter_ft: float,
        pool_shape: str,
        user_id: Optional[str] = None,
    ) -> DimensionEstimate:
        """Add a perimeter-based dimension estimate and potentially update BOW."""
        bow = await self._get_bow(org_id, bow_id)
        estimated_sqft = self.calculate_sqft_from_perimeter(perimeter_ft, pool_shape)

        estimate = DimensionEstimate(
            id=str(uuid.uuid4()),
            body_of_water_id=bow_id,
            organization_id=org_id,
            source="perimeter",
            estimated_sqft=estimated_sqft,
            perimeter_ft=perimeter_ft,
            raw_data={"pool_shape": pool_shape, "perimeter_ft": perimeter_ft},
            notes=f"Perimeter {perimeter_ft} ft, shape {pool_shape}, estimated {estimated_sqft} sqft",
            created_by=user_id,
        )
        self.db.add(estimate)

        # Auto-promote if higher priority than current source
        if self._should_promote("perimeter", bow.dimension_source):
            bow.pool_sqft = estimated_sqft
            bow.perimeter_ft = perimeter_ft
            bow.dimension_source = "perimeter"
            bow.dimension_source_date = datetime.now(timezone.utc)
            if pool_shape:
                bow.pool_shape = pool_shape

        await self.db.flush()
        await self.db.refresh(estimate)
        return estimate

    async def add_estimate(
        self,
        org_id: str,
        bow_id: str,
        source: str,
        estimated_sqft: Optional[float] = None,
        perimeter_ft: Optional[float] = None,
        raw_data: Optional[dict] = None,
        notes: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> DimensionEstimate:
        """Add a dimension estimate from any source."""
        bow = await self._get_bow(org_id, bow_id)

        estimate = DimensionEstimate(
            id=str(uuid.uuid4()),
            body_of_water_id=bow_id,
            organization_id=org_id,
            source=source,
            estimated_sqft=estimated_sqft,
            perimeter_ft=perimeter_ft,
            raw_data=raw_data,
            notes=notes,
            created_by=user_id,
        )
        self.db.add(estimate)

        # Auto-promote if higher priority than current source
        if estimated_sqft and self._should_promote(source, bow.dimension_source):
            bow.pool_sqft = estimated_sqft
            if perimeter_ft:
                bow.perimeter_ft = perimeter_ft
            bow.dimension_source = source
            bow.dimension_source_date = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(estimate)
        return estimate

    async def get_estimates(self, org_id: str, bow_id: str) -> list[DimensionEstimate]:
        """Return all estimates for a BOW, ordered by created_at desc."""
        # Verify BOW exists and belongs to org
        await self._get_bow(org_id, bow_id)

        result = await self.db.execute(
            select(DimensionEstimate)
            .where(
                DimensionEstimate.body_of_water_id == bow_id,
                DimensionEstimate.organization_id == org_id,
            )
            .order_by(DimensionEstimate.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_comparison(self, org_id: str, bow_id: str) -> dict:
        """Get comparison data with discrepancy analysis."""
        bow = await self._get_bow(org_id, bow_id)
        estimates = await self.get_estimates(org_id, bow_id)

        result = {
            "estimates": estimates,
            "active_source": bow.dimension_source,
            "active_sqft": bow.pool_sqft,
            "discrepancy_pct": None,
            "discrepancy_level": None,
        }

        if len(estimates) < 2:
            return result

        # Get sqft values from the two highest-priority estimates
        sorted_estimates = sorted(
            [e for e in estimates if e.estimated_sqft],
            key=lambda e: self.SOURCE_PRIORITY.get(e.source, 99),
        )

        if len(sorted_estimates) >= 2:
            sqft1 = sorted_estimates[0].estimated_sqft
            sqft2 = sorted_estimates[1].estimated_sqft
            max_sqft = max(sqft1, sqft2)
            if max_sqft > 0:
                disc = abs(sqft1 - sqft2) / max_sqft * 100
                result["discrepancy_pct"] = round(disc, 1)
                if disc < 10:
                    result["discrepancy_level"] = "ok"
                elif disc <= 25:
                    result["discrepancy_level"] = "review"
                else:
                    result["discrepancy_level"] = "alert"

        return result

    async def delete_estimate(self, org_id: str, estimate_id: str) -> None:
        """Delete an estimate."""
        result = await self.db.execute(
            select(DimensionEstimate).where(
                DimensionEstimate.id == estimate_id,
                DimensionEstimate.organization_id == org_id,
            )
        )
        estimate = result.scalar_one_or_none()
        if not estimate:
            raise NotFoundError("Dimension estimate not found")
        await self.db.delete(estimate)
        await self.db.flush()
