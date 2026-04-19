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
from src.services.events.platform_event_service import Actor, PlatformEventService
from src.services.events.actor_factory import actor_system


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

    async def complete(
        self, org_id: str, visit_id: str, *,
        actor: Optional[Actor] = None, **kwargs,
    ) -> Visit:
        visit = await self.get(org_id, visit_id)
        now = datetime.now(timezone.utc)
        visit.status = VisitStatus.completed.value
        visit.actual_departure = now
        if not visit.actual_arrival:
            visit.actual_arrival = now
        if visit.started_at:
            delta = now - visit.started_at
            visit.duration_minutes = int(delta.total_seconds() / 60)
        for key, value in kwargs.items():
            if value is not None:
                setattr(visit, key, value)
        await self.db.flush()

        refs = {"visit_id": visit.id}
        if visit.property_id:
            refs["property_id"] = visit.property_id
        if visit.customer_id:
            refs["customer_id"] = visit.customer_id
        await PlatformEventService.emit(
            db=self.db,
            event_type="visit.completed",
            level="user_action" if actor and actor.actor_type == "user" else "system_action",
            actor=actor or actor_system(),
            organization_id=org_id,
            entity_refs=refs,
            payload={"duration_minutes": visit.duration_minutes} if visit.duration_minutes is not None else {},
        )

        # Activation funnel — first-visit-completed.
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_visit_completed",
            organization_id=org_id,
            entity_refs={"visit_id": visit.id, "property_id": visit.property_id},
            source="visit_service",
        )

        await self.db.refresh(visit)
        return visit

    async def today(self, org_id: str, tech_id: Optional[str] = None) -> List[dict]:
        today = date.today()
        visits, _ = await self.list(org_id, scheduled_date=today, tech_id=tech_id, limit=100)
        return visits
