"""Base presenter with shared helpers for FK resolution."""

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.customer import Customer
from src.models.property import Property


class Presenter:
    """Base presenter. All data leaving the system passes through a presenter."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def one(self, model) -> dict:
        raise NotImplementedError

    async def many(self, models: list) -> list[dict]:
        return [await self.one(m) for m in models]

    @staticmethod
    def _iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    async def _load_customers(self, ids: set[str]) -> dict[str, Customer]:
        """Batch load customers by ID. Returns {id: Customer}."""
        if not ids:
            return {}
        result = await self.db.execute(
            select(Customer).where(Customer.id.in_(list(ids)))
        )
        return {c.id: c for c in result.scalars().all()}

    async def _load_customer_addresses(self, ids: set[str]) -> dict[str, str]:
        """Batch load first active property address per customer. Returns {customer_id: "address, city"}."""
        if not ids:
            return {}
        addresses = {}
        for cid in ids:
            result = await self.db.execute(
                select(Property).where(
                    Property.customer_id == cid,
                    Property.is_active == True,
                ).limit(1)
            )
            prop = result.scalar_one_or_none()
            if prop:
                addresses[cid] = f"{prop.address}, {prop.city}"
        return addresses
