"""Centralized rate sync: WF → Property → Customer.

Call `sync_rates_for_property(db, property_id)` after ANY rate change
on WFs or properties. It ensures the full chain stays consistent.
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.models.customer import Customer


async def sync_rates_for_property(db: AsyncSession, property_id: str) -> None:
    """Sync Property.monthly_rate from WF sum, then Customer.monthly_rate from Property sum."""
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if not prop:
        return

    # Property rate = sum of active WF rates
    result = await db.execute(
        select(func.coalesce(func.sum(WaterFeature.monthly_rate), 0))
        .where(WaterFeature.property_id == property_id, WaterFeature.is_active == True)
    )
    prop.monthly_rate = round(result.scalar() or 0, 2)

    # Customer rate = sum of all property rates
    result = await db.execute(
        select(func.coalesce(func.sum(Property.monthly_rate), 0))
        .where(Property.customer_id == prop.customer_id)
    )
    customer_total = round(result.scalar() or 0, 2)

    result = await db.execute(select(Customer).where(Customer.id == prop.customer_id))
    customer = result.scalar_one_or_none()
    if customer:
        customer.monthly_rate = customer_total

    await db.flush()


async def sync_rates_for_customer(db: AsyncSession, customer_id: str) -> None:
    """Sync all properties and customer rate for a given customer."""
    result = await db.execute(
        select(Property).where(Property.customer_id == customer_id)
    )
    props = result.scalars().all()
    for prop in props:
        # Property rate = sum of active WF rates
        result = await db.execute(
            select(func.coalesce(func.sum(WaterFeature.monthly_rate), 0))
            .where(WaterFeature.property_id == prop.id, WaterFeature.is_active == True)
        )
        prop.monthly_rate = round(result.scalar() or 0, 2)

    # Customer rate = sum of all property rates
    result = await db.execute(
        select(func.coalesce(func.sum(Property.monthly_rate), 0))
        .where(Property.customer_id == customer_id)
    )
    customer_total = round(result.scalar() or 0, 2)

    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if customer:
        customer.monthly_rate = customer_total

    await db.flush()
