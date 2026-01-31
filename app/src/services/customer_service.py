"""Customer service — CRUD operations scoped by organization."""

import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from src.models.customer import Customer
from src.models.property import Property
from src.core.exceptions import NotFoundError


class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, org_id: str, search: Optional[str] = None, is_active: Optional[bool] = None,
        skip: int = 0, limit: int = 50,
    ) -> tuple[List[Customer], int]:
        query = select(Customer).where(Customer.organization_id == org_id)
        count_query = select(func.count(Customer.id)).where(Customer.organization_id == org_id)

        if is_active is not None:
            query = query.where(Customer.is_active == is_active)
            count_query = count_query.where(Customer.is_active == is_active)
        if search:
            search_filter = f"%{search}%"
            query = query.where(
                (Customer.first_name.ilike(search_filter))
                | (Customer.last_name.ilike(search_filter))
                | (Customer.company_name.ilike(search_filter))
                | (Customer.email.ilike(search_filter))
            )
            count_query = count_query.where(
                (Customer.first_name.ilike(search_filter))
                | (Customer.last_name.ilike(search_filter))
                | (Customer.company_name.ilike(search_filter))
                | (Customer.email.ilike(search_filter))
            )

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(Customer.last_name, Customer.first_name).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get(self, org_id: str, customer_id: str) -> Customer:
        result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")
        return customer

    async def create(self, org_id: str, **kwargs) -> Customer:
        customer = Customer(id=str(uuid.uuid4()), organization_id=org_id, **kwargs)
        self.db.add(customer)
        await self.db.flush()
        await self.db.refresh(customer)
        return customer

    async def update(self, org_id: str, customer_id: str, **kwargs) -> Customer:
        customer = await self.get(org_id, customer_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(customer, key, value)
        await self.db.flush()
        await self.db.refresh(customer)
        return customer

    async def delete(self, org_id: str, customer_id: str) -> None:
        customer = await self.get(org_id, customer_id)
        await self.db.delete(customer)
        await self.db.flush()

    async def get_property_count(self, customer_id: str) -> int:
        result = await self.db.execute(
            select(func.count(Property.id)).where(Property.customer_id == customer_id)
        )
        return result.scalar() or 0
