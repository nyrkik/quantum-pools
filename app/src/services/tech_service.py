"""Tech service — CRUD operations."""

import uuid
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.tech import Tech
from src.core.exceptions import NotFoundError


class TechService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, org_id: str, is_active: Optional[bool] = None) -> List[Tech]:
        query = select(Tech).where(Tech.organization_id == org_id)
        if is_active is not None:
            query = query.where(Tech.is_active == is_active)
        result = await self.db.execute(query.order_by(Tech.first_name))
        return list(result.scalars().all())

    async def get(self, org_id: str, tech_id: str) -> Tech:
        result = await self.db.execute(
            select(Tech).where(Tech.id == tech_id, Tech.organization_id == org_id)
        )
        tech = result.scalar_one_or_none()
        if not tech:
            raise NotFoundError("Tech not found")
        return tech

    async def create(self, org_id: str, **kwargs) -> Tech:
        tech = Tech(id=str(uuid.uuid4()), organization_id=org_id, **kwargs)
        self.db.add(tech)
        await self.db.flush()
        await self.db.refresh(tech)
        return tech

    async def update(self, org_id: str, tech_id: str, **kwargs) -> Tech:
        tech = await self.get(org_id, tech_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(tech, key, value)
        await self.db.flush()
        await self.db.refresh(tech)
        return tech

    async def delete(self, org_id: str, tech_id: str) -> None:
        tech = await self.get(org_id, tech_id)
        await self.db.delete(tech)
        await self.db.flush()
