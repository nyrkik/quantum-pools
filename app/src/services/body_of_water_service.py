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
            .order_by(BodyOfWater.is_primary.desc(), BodyOfWater.water_type, BodyOfWater.name)
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

        # If this is set as primary, unset any existing primary
        if kwargs.get("is_primary"):
            await self._clear_primary(org_id, property_id)

        # If first BOW for property, make it primary
        count_result = await self.db.execute(
            select(func.count(BodyOfWater.id)).where(
                BodyOfWater.property_id == property_id,
                BodyOfWater.organization_id == org_id,
            )
        )
        if (count_result.scalar() or 0) == 0:
            kwargs["is_primary"] = True

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

        # If setting as primary, unset existing primary
        if kwargs.get("is_primary"):
            await self._clear_primary(org_id, bow.property_id, exclude_id=bow_id)

        for key, value in kwargs.items():
            if value is not None:
                setattr(bow, key, value)
        await self.db.flush()
        await self.db.refresh(bow)
        return bow

    async def delete(self, org_id: str, bow_id: str) -> None:
        bow = await self.get(org_id, bow_id)
        was_primary = bow.is_primary
        property_id = bow.property_id
        await self.db.delete(bow)
        await self.db.flush()

        # If deleted was primary, promote another BOW if one exists
        if was_primary:
            result = await self.db.execute(
                select(BodyOfWater)
                .where(
                    BodyOfWater.property_id == property_id,
                    BodyOfWater.organization_id == org_id,
                )
                .order_by(BodyOfWater.created_at)
                .limit(1)
            )
            next_bow = result.scalar_one_or_none()
            if next_bow:
                next_bow.is_primary = True
                await self.db.flush()

    async def get_primary_for_property(self, org_id: str, property_id: str) -> Optional[BodyOfWater]:
        result = await self.db.execute(
            select(BodyOfWater).where(
                BodyOfWater.property_id == property_id,
                BodyOfWater.organization_id == org_id,
                BodyOfWater.is_primary == True,
            )
        )
        return result.scalar_one_or_none()

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

    async def _clear_primary(self, org_id: str, property_id: str, exclude_id: Optional[str] = None) -> None:
        query = select(BodyOfWater).where(
            BodyOfWater.property_id == property_id,
            BodyOfWater.organization_id == org_id,
            BodyOfWater.is_primary == True,
        )
        if exclude_id:
            query = query.where(BodyOfWater.id != exclude_id)
        result = await self.db.execute(query)
        for bow in result.scalars().all():
            bow.is_primary = False
        await self.db.flush()
