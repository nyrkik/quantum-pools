"""Property service — CRUD with auto-geocoding."""

import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.property import Property
from src.core.exceptions import NotFoundError


class PropertyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, org_id: str, customer_id: Optional[str] = None, is_active: Optional[bool] = None,
        skip: int = 0, limit: int = 50,
    ) -> tuple[List[Property], int]:
        query = select(Property).where(Property.organization_id == org_id)
        count_query = select(func.count(Property.id)).where(Property.organization_id == org_id)

        if customer_id:
            query = query.where(Property.customer_id == customer_id)
            count_query = count_query.where(Property.customer_id == customer_id)
        if is_active is not None:
            query = query.where(Property.is_active == is_active)
            count_query = count_query.where(Property.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(query.order_by(Property.address).offset(skip).limit(limit))
        return list(result.scalars().all()), total

    async def get(self, org_id: str, property_id: str) -> Property:
        result = await self.db.execute(
            select(Property).where(Property.id == property_id, Property.organization_id == org_id)
        )
        prop = result.scalar_one_or_none()
        if not prop:
            raise NotFoundError("Property not found")
        return prop

    async def create(self, org_id: str, **kwargs) -> Property:
        prop = Property(id=str(uuid.uuid4()), organization_id=org_id, **kwargs)
        self.db.add(prop)
        await self.db.flush()
        await self.db.refresh(prop)
        return prop

    async def update(self, org_id: str, property_id: str, **kwargs) -> Property:
        prop = await self.get(org_id, property_id)
        address_changed = False
        for key, value in kwargs.items():
            if value is not None:
                if key in ("address", "city", "state", "zip_code"):
                    address_changed = True
                setattr(prop, key, value)
        await self.db.flush()
        await self.db.refresh(prop)
        return prop, address_changed

    async def delete(self, org_id: str, property_id: str) -> None:
        prop = await self.get(org_id, property_id)
        await self.db.delete(prop)
        await self.db.flush()

    async def update_geocode(self, property_id: str, lat: float, lng: float, provider: str) -> None:
        result = await self.db.execute(select(Property).where(Property.id == property_id))
        prop = result.scalar_one_or_none()
        if prop:
            prop.lat = lat
            prop.lng = lng
            prop.geocode_provider = provider
            await self.db.flush()
