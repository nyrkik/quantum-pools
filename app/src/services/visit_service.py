"""Visit service — scheduling and completion."""

import uuid
from typing import Optional, List
from datetime import datetime, timezone, date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from src.models.visit import Visit, VisitStatus
from src.models.property import Property
from src.models.tech import Tech
from src.models.customer import Customer
from src.core.exceptions import NotFoundError


class VisitService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, org_id: str, scheduled_date: Optional[date] = None, tech_id: Optional[str] = None,
        property_id: Optional[str] = None, status: Optional[str] = None,
        skip: int = 0, limit: int = 50,
    ) -> tuple[List[dict], int]:
        query = (
            select(Visit, Property, Tech, Customer)
            .join(Property, Visit.property_id == Property.id)
            .outerjoin(Tech, Visit.tech_id == Tech.id)
            .join(Customer, Property.customer_id == Customer.id)
            .where(Visit.organization_id == org_id)
        )
        count_query = select(func.count(Visit.id)).where(Visit.organization_id == org_id)

        if scheduled_date:
            query = query.where(Visit.scheduled_date == scheduled_date)
            count_query = count_query.where(Visit.scheduled_date == scheduled_date)
        if tech_id:
            query = query.where(Visit.tech_id == tech_id)
            count_query = count_query.where(Visit.tech_id == tech_id)
        if property_id:
            query = query.where(Visit.property_id == property_id)
            count_query = count_query.where(Visit.property_id == property_id)
        if status:
            query = query.where(Visit.status == status)
            count_query = count_query.where(Visit.status == status)

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(Visit.scheduled_date.desc(), Visit.created_at.desc()).offset(skip).limit(limit)
        )

        visits = []
        for visit, prop, tech, customer in result.all():
            visits.append({
                "visit": visit,
                "property_address": prop.full_address,
                "tech_name": tech.full_name if tech else None,
                "customer_name": customer.full_name,
            })
        return visits, total

    async def get(self, org_id: str, visit_id: str) -> Visit:
        result = await self.db.execute(
            select(Visit).where(Visit.id == visit_id, Visit.organization_id == org_id)
        )
        visit = result.scalar_one_or_none()
        if not visit:
            raise NotFoundError("Visit not found")
        return visit

    async def create(self, org_id: str, **kwargs) -> Visit:
        visit = Visit(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            status=VisitStatus.scheduled.value,
            **kwargs,
        )
        self.db.add(visit)
        await self.db.flush()
        await self.db.refresh(visit)
        return visit

    async def update(self, org_id: str, visit_id: str, **kwargs) -> Visit:
        visit = await self.get(org_id, visit_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(visit, key, value)
        await self.db.flush()
        await self.db.refresh(visit)
        return visit

    async def complete(self, org_id: str, visit_id: str, **kwargs) -> Visit:
        visit = await self.get(org_id, visit_id)
        visit.status = VisitStatus.completed.value
        visit.actual_departure = datetime.now(timezone.utc)
        if not visit.actual_arrival:
            visit.actual_arrival = visit.actual_departure
        for key, value in kwargs.items():
            if value is not None:
                setattr(visit, key, value)
        await self.db.flush()
        await self.db.refresh(visit)
        return visit

    async def today(self, org_id: str, tech_id: Optional[str] = None) -> List[dict]:
        today = date.today()
        visits, _ = await self.list(org_id, scheduled_date=today, tech_id=tech_id, limit=100)
        return visits
