"""Customer service — CRUD operations scoped by organization."""

import uuid
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload

from src.models.customer import Customer
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.core.exceptions import NotFoundError


class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    SORT_COLUMNS = {
        "name": (Customer.first_name, Customer.last_name),
        "company": (Customer.company_name,),
        "rate": (Customer.monthly_rate,),
        "balance": (Customer.balance,),
        "status": (Customer.status,),
    }

    async def list(
        self, org_id: str, search: Optional[str] = None, is_active: Optional[bool] = None,
        status: Optional[List[str]] = None, customer_type: Optional[str] = None,
        sort_by: str = "name", sort_dir: str = "asc",
        skip: int = 0, limit: int = 50,
    ) -> tuple[List[Customer], int]:
        query = select(Customer).where(Customer.organization_id == org_id)
        count_query = select(func.count(Customer.id)).where(Customer.organization_id == org_id)

        if customer_type:
            query = query.where(Customer.customer_type == customer_type)
            count_query = count_query.where(Customer.customer_type == customer_type)
        if status:
            query = query.where(Customer.status.in_(status))
            count_query = count_query.where(Customer.status.in_(status))
        elif is_active is not None:
            query = query.where(Customer.is_active == is_active)
            count_query = count_query.where(Customer.is_active == is_active)
        if search:
            search_filter = f"%{search}%"
            # Match customers whose properties (service addresses) hit the search — via EXISTS
            # to avoid duplicates from the join.
            property_match = (
                select(Property.id)
                .where(
                    Property.customer_id == Customer.id,
                    or_(
                        Property.address.ilike(search_filter),
                        Property.city.ilike(search_filter),
                        Property.name.ilike(search_filter),
                    ),
                )
                .exists()
            )
            search_clause = (
                Customer.first_name.ilike(search_filter)
                | Customer.last_name.ilike(search_filter)
                | Customer.company_name.ilike(search_filter)
                | Customer.display_name_col.ilike(search_filter)
                | Customer.email.ilike(search_filter)
                | Customer.billing_address.ilike(search_filter)
                | Customer.billing_city.ilike(search_filter)
                | property_match
            )
            query = query.where(search_clause)
            count_query = count_query.where(search_clause)

        # Server-side sorting
        from sqlalchemy import asc, desc
        order_fn = desc if sort_dir == "desc" else asc
        sort_cols = self.SORT_COLUMNS.get(sort_by, (Customer.first_name, Customer.last_name))
        for col in sort_cols:
            query = query.order_by(order_fn(col))

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(query.offset(skip).limit(limit))
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

        # Activation funnel: first-customer-added for this org.
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_customer_added",
            organization_id=org_id,
            entity_refs={"customer_id": customer.id},
            source="customer_service",
        )

        await self.db.refresh(customer)
        return customer

    async def update(self, org_id: str, customer_id: str, **kwargs) -> Customer:
        customer = await self.get(org_id, customer_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(customer, key, value)
        # Keep is_active in sync with status
        # service_call customers are active (they're serviced, just not recurring)
        if "status" in kwargs and kwargs["status"] is not None:
            customer.is_active = kwargs["status"] in ("active", "service_call")
        await self.db.flush()
        await self.db.refresh(customer)
        return customer

    async def delete(self, org_id: str, customer_id: str) -> None:
        customer = await self.get(org_id, customer_id)
        await self.db.delete(customer)
        await self.db.flush()

    async def create_with_property(
        self, org_id: str,
        customer_data: dict,
        property_data: dict,
        bow_data: dict,
    ) -> Tuple[Customer, Property]:
        """Atomically create customer + property + primary WF."""
        customer_id = str(uuid.uuid4())
        property_id = str(uuid.uuid4())
        wf_id = str(uuid.uuid4())

        customer = Customer(id=customer_id, organization_id=org_id, **customer_data)
        self.db.add(customer)

        prop = Property(
            id=property_id,
            organization_id=org_id,
            customer_id=customer_id,
            **property_data,
        )
        self.db.add(prop)

        wf = WaterFeature(
            id=wf_id,
            organization_id=org_id,
            property_id=property_id,
            **bow_data,
        )
        self.db.add(wf)

        await self.db.flush()

        # Activation funnel — covers the create_with_property entry point too.
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_customer_added",
            organization_id=org_id,
            entity_refs={"customer_id": customer.id, "property_id": prop.id},
            source="customer_service_with_property",
        )

        await self.db.refresh(customer)
        await self.db.refresh(prop)
        return customer, prop

    async def get_property_count(self, customer_id: str) -> int:
        result = await self.db.execute(
            select(func.count(Property.id)).where(Property.customer_id == customer_id)
        )
        return result.scalar() or 0

    async def get_first_property(self, customer_id: str):
        result = await self.db.execute(
            select(Property).where(Property.customer_id == customer_id)
            .order_by(Property.created_at).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_first_property_address(self, customer_id: str) -> Optional[str]:
        result = await self.db.execute(
            select(Property.address).where(Property.customer_id == customer_id)
            .order_by(Property.created_at).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_first_property_pool_type(self, customer_id: str) -> Optional[str]:
        result = await self.db.execute(
            select(WaterFeature.pool_type)
            .join(Property, Property.id == WaterFeature.property_id)
            .where(Property.customer_id == customer_id)
            .order_by(Property.created_at)
            .limit(1)
        )
        bow_type = result.scalar_one_or_none()
        if bow_type:
            return bow_type
        result = await self.db.execute(
            select(Property.pool_type).where(Property.customer_id == customer_id)
            .order_by(Property.created_at).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_property_wf_summary(self, customer_id: str) -> Optional[str]:
        """Return WF summary for customer's first property, e.g. 'Pool, Spa'."""
        result = await self.db.execute(
            select(Property.id).where(Property.customer_id == customer_id)
            .order_by(Property.created_at).limit(1)
        )
        prop_id = result.scalar_one_or_none()
        if not prop_id:
            return None
        bow_result = await self.db.execute(
            select(WaterFeature.water_type).where(
                WaterFeature.property_id == prop_id,
                WaterFeature.is_active == True,
            ).order_by(WaterFeature.water_type)
        )
        types = [r[0] for r in bow_result.all()]
        if not types:
            return None
        parts = []
        pool_count = sum(1 for t in types if t == "pool")
        spa_count = sum(1 for t in types if t == "spa")
        other = [t.replace("_", " ").title() for t in types if t not in ("pool", "spa")]
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
