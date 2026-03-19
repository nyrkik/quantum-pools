"""BodyOfWater service — CRUD for bodies of water within properties."""

import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.body_of_water import BodyOfWater
from src.models.property import Property
from src.core.exceptions import NotFoundError


class BodyOfWaterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_property(self, org_id: str, property_id: str) -> List[BodyOfWater]:
        result = await self.db.execute(
            select(BodyOfWater)
            .where(
                BodyOfWater.organization_id == org_id,
                BodyOfWater.property_id == property_id,
            )
            .order_by(BodyOfWater.water_type, BodyOfWater.name)
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, bow_id: str) -> BodyOfWater:
        result = await self.db.execute(
            select(BodyOfWater).where(BodyOfWater.id == bow_id, BodyOfWater.organization_id == org_id)
        )
        bow = result.scalar_one_or_none()
        if not bow:
            raise NotFoundError("Body of water not found")
        return bow

    async def create(self, org_id: str, property_id: str, **kwargs) -> BodyOfWater:
        # Verify property exists and belongs to org
        prop_result = await self.db.execute(
            select(Property).where(Property.id == property_id, Property.organization_id == org_id)
        )
        if not prop_result.scalar_one_or_none():
            raise NotFoundError("Property not found")

        kwargs.pop("is_primary", None)

        # Water-type-aware service time defaults
        if "estimated_service_minutes" not in kwargs or kwargs.get("estimated_service_minutes") is None:
            wt = kwargs.get("water_type", "pool")
            defaults = {"pool": 30, "spa": 10, "hot_tub": 10, "wading_pool": 10, "fountain": 15, "water_feature": 15}
            kwargs["estimated_service_minutes"] = defaults.get(wt, 30)

        # Water-type-aware gallons defaults
        if "pool_gallons" not in kwargs or kwargs.get("pool_gallons") is None:
            wt = kwargs.get("water_type", "pool")
            gal_defaults = {"spa": 1000, "hot_tub": 500, "wading_pool": 500, "fountain": 500, "water_feature": 200}
            if wt in gal_defaults:
                kwargs["pool_gallons"] = gal_defaults[wt]

        bow = BodyOfWater(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            property_id=property_id,
            **kwargs,
        )
        self.db.add(bow)
        await self.db.flush()
        await self.db.refresh(bow)
        return bow

    async def update(self, org_id: str, bow_id: str, **kwargs) -> BodyOfWater:
        bow = await self.get(org_id, bow_id)
        kwargs.pop("is_primary", None)

        for key, value in kwargs.items():
            if value is not None:
                setattr(bow, key, value)
        await self.db.flush()
        await self.db.refresh(bow)
        return bow

    async def delete(self, org_id: str, bow_id: str) -> None:
        bow = await self.get(org_id, bow_id)
        await self.db.delete(bow)
        await self.db.flush()

    async def get_bow_summary(self, org_id: str, property_id: str) -> str:
        """Return a human-readable summary like 'Pool, Spa' or '2 Pools'."""
        bows = await self.list_for_property(org_id, property_id)
        if not bows:
            return ""
        types = [b.water_type for b in bows if b.is_active]
        pool_count = sum(1 for t in types if t == "pool")
        spa_count = sum(1 for t in types if t == "spa")
        other = [t.replace("_", " ").title() for t in types if t not in ("pool", "spa")]

        parts = []
        if pool_count == 1:
            parts.append("Pool")
        elif pool_count > 1:
            parts.append(f"{pool_count} Pools")
        if spa_count == 1:
            parts.append("Spa")
        elif spa_count > 1:
            parts.append(f"{spa_count} Spas")
        parts.extend(other)
        return ", ".join(parts)

    async def get_total_service_minutes(self, org_id: str, property_id: str) -> int:
        """Sum estimated_service_minutes across all active BOWs for a property."""
        result = await self.db.execute(
            select(func.sum(BodyOfWater.estimated_service_minutes)).where(
                BodyOfWater.property_id == property_id,
                BodyOfWater.organization_id == org_id,
                BodyOfWater.is_active == True,
            )
        )
        return result.scalar() or 30

    async def get_total_gallons(self, org_id: str, property_id: str) -> Optional[int]:
        """Sum pool_gallons across all active BOWs for a property."""
        result = await self.db.execute(
            select(func.sum(BodyOfWater.pool_gallons)).where(
                BodyOfWater.property_id == property_id,
                BodyOfWater.organization_id == org_id,
                BodyOfWater.is_active == True,
            )
        )
        return result.scalar()
