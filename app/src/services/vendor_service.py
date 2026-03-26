"""Vendor service — business logic for vendor CRUD and defaults."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.vendor import Vendor


class VendorService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_vendors(self, org_id: str, active_only: bool = True) -> list[dict]:
        q = select(Vendor).where(Vendor.organization_id == org_id)
        if active_only:
            q = q.where(Vendor.is_active == True)
        q = q.order_by(Vendor.sort_order, Vendor.name)
        result = await self.db.execute(q)
        return [self._to_dict(v) for v in result.scalars().all()]

    async def create_vendor(self, org_id: str, **kwargs) -> dict:
        vendor = Vendor(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            name=kwargs["name"],
            provider_type=kwargs.get("provider_type", "generic"),
            portal_url=kwargs.get("portal_url"),
            search_url_template=kwargs.get("search_url_template"),
            account_number=kwargs.get("account_number"),
            is_active=True,
            sort_order=kwargs.get("sort_order", 0),
        )
        self.db.add(vendor)
        await self.db.flush()
        return self._to_dict(vendor)

    async def update_vendor(self, org_id: str, vendor_id: str, **kwargs) -> dict:
        result = await self.db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.organization_id == org_id)
        )
        vendor = result.scalar_one_or_none()
        if not vendor:
            raise ValueError("Vendor not found")

        for key in ("name", "provider_type", "portal_url", "search_url_template",
                     "account_number", "is_active", "sort_order"):
            if key in kwargs:
                setattr(vendor, key, kwargs[key])
        vendor.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return self._to_dict(vendor)

    async def delete_vendor(self, org_id: str, vendor_id: str) -> bool:
        """Soft delete — marks vendor inactive."""
        result = await self.db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.organization_id == org_id)
        )
        vendor = result.scalar_one_or_none()
        if not vendor:
            return False
        vendor.is_active = False
        vendor.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    async def get_search_url(self, org_id: str, vendor_id: str, query: str) -> str | None:
        result = await self.db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.organization_id == org_id)
        )
        vendor = result.scalar_one_or_none()
        if not vendor or not vendor.search_url_template:
            return None
        return vendor.search_url_template.replace("{query}", query)

    async def seed_defaults(self, org_id: str) -> list[dict]:
        """Create SCP default vendor if none exist for org."""
        existing = await self.db.execute(
            select(Vendor).where(Vendor.organization_id == org_id).limit(1)
        )
        if existing.scalar_one_or_none():
            return []

        defaults = [
            Vendor(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                name="SCP Distributors",
                provider_type="scp",
                portal_url="https://www.pool360.com",
                search_url_template="https://www.pool360.com/Catalog/Search?q={query}",
                is_active=True,
                sort_order=0,
            ),
        ]
        for v in defaults:
            self.db.add(v)
        await self.db.flush()
        return [self._to_dict(v) for v in defaults]

    @staticmethod
    def _to_dict(v: Vendor) -> dict:
        return {
            "id": v.id,
            "organization_id": v.organization_id,
            "name": v.name,
            "provider_type": v.provider_type,
            "portal_url": v.portal_url,
            "search_url_template": v.search_url_template,
            "account_number": v.account_number,
            "is_active": v.is_active,
            "sort_order": v.sort_order,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        }
