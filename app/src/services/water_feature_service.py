"""WaterFeature service — CRUD for bodies of water within properties."""

import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.water_feature import WaterFeature
from src.models.property import Property
from src.models.customer import Customer
from src.core.exceptions import NotFoundError
from src.services.rate_sync import sync_rates_for_property


class WaterFeatureService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_property(self, org_id: str, property_id: str) -> List[WaterFeature]:
        result = await self.db.execute(
            select(WaterFeature)
            .where(
                WaterFeature.organization_id == org_id,
                WaterFeature.property_id == property_id,
            )
            .order_by(WaterFeature.water_type, WaterFeature.name)
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, wf_id: str) -> WaterFeature:
        result = await self.db.execute(
            select(WaterFeature).where(WaterFeature.id == wf_id, WaterFeature.organization_id == org_id)
        )
        wf = result.scalar_one_or_none()
        if not wf:
            raise NotFoundError("Body of water not found")
        return wf

    async def create(self, org_id: str, property_id: str, **kwargs) -> WaterFeature:
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

        # Don't let the new WF's rate inflate the customer total
        # The customer rate is the contract — adding a WF splits it, not adds to it
        new_bow_rate = kwargs.pop("monthly_rate", None)

        wf = WaterFeature(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            property_id=property_id,
            **kwargs,
        )
        self.db.add(wf)
        await self.db.flush()
        await self.db.refresh(wf)

        # Reallocate customer rate across all WFs (including new one)
        await self._reallocate_customer_rate(property_id, org_id)

        await self.db.refresh(wf)
        return wf

    async def update(self, org_id: str, wf_id: str, **kwargs) -> WaterFeature:
        wf = await self.get(org_id, wf_id)
        kwargs.pop("is_primary", None)

        for key, value in kwargs.items():
            if value is not None:
                setattr(wf, key, value)
        await self.db.flush()
        await self.db.refresh(wf)

        # Sync property + customer rates if WF rate changed
        if "monthly_rate" in kwargs:
            await sync_rates_for_property(self.db, wf.property_id)

        return wf

    async def delete(self, org_id: str, wf_id: str) -> None:
        wf = await self.get(org_id, wf_id)
        property_id = wf.property_id
        await self.db.delete(wf)
        await self.db.flush()
        await sync_rates_for_property(self.db, property_id)

    async def _reallocate_customer_rate(self, property_id: str, org_id: str) -> None:
        """Reallocate the property's rate across its active WFs."""
        from src.services.profitability_service import ProfitabilityService

        result = await self.db.execute(
            select(Property).where(Property.id == property_id)
        )
        prop = result.scalar_one_or_none()
        if not prop:
            return

        rate_to_split = prop.monthly_rate
        if not rate_to_split:
            # Fall back to customer rate if property has no rate yet
            result = await self.db.execute(
                select(Customer).where(Customer.id == prop.customer_id)
            )
            customer = result.scalar_one_or_none()
            if not customer or not customer.monthly_rate:
                return
            rate_to_split = customer.monthly_rate

        # Get active WFs for this property only
        bows_result = await self.db.execute(
            select(WaterFeature).where(
                WaterFeature.property_id == property_id,
                WaterFeature.is_active == True,
            )
        )
        wfs = bows_result.scalars().all()

        if not wfs:
            return

        allocation = ProfitabilityService.allocate_rate_to_wfs(rate_to_split, wfs)
        for wf in wfs:
            alloc = allocation.get(wf.id, {})
            wf.monthly_rate = alloc.get("allocated_rate", rate_to_split / len(wfs))
            wf.rate_allocation_method = alloc.get("allocation_method", "equal")

        await self.db.flush()
        await sync_rates_for_property(self.db, property_id)

    async def get_wf_summary(self, org_id: str, property_id: str) -> str:
        """Return a human-readable summary like 'Pool, Spa' or '2 Pools'."""
        wfs = await self.list_for_property(org_id, property_id)
        if not wfs:
            return ""
        types = [b.water_type for b in wfs if b.is_active]
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
        """Sum estimated_service_minutes across all active WFs for a property."""
        result = await self.db.execute(
            select(func.sum(WaterFeature.estimated_service_minutes)).where(
                WaterFeature.property_id == property_id,
                WaterFeature.organization_id == org_id,
                WaterFeature.is_active == True,
            )
        )
        return result.scalar() or 30

    async def get_total_gallons(self, org_id: str, property_id: str) -> Optional[int]:
        """Sum pool_gallons across all active WFs for a property."""
        result = await self.db.execute(
            select(func.sum(WaterFeature.pool_gallons)).where(
                WaterFeature.property_id == property_id,
                WaterFeature.organization_id == org_id,
                WaterFeature.is_active == True,
            )
        )
        return result.scalar()
