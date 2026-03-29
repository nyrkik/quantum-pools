"""Parts search service — full-text search on parts_catalog."""

from typing import Optional

from sqlalchemy import select, or_, func, distinct, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.parts_catalog import PartsCatalog


class PartsSearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        query: str,
        vendor_provider: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search on parts_catalog using ILIKE across multiple fields."""
        q = select(PartsCatalog)

        if vendor_provider:
            q = q.where(PartsCatalog.vendor_provider == vendor_provider)
        if category:
            q = q.where(PartsCatalog.category == category)
        if brand:
            q = q.where(PartsCatalog.brand == brand)

        if query.strip():
            pattern = f"%{query.strip()}%"
            q = q.where(
                or_(
                    PartsCatalog.name.ilike(pattern),
                    PartsCatalog.sku.ilike(pattern),
                    PartsCatalog.brand.ilike(pattern),
                    PartsCatalog.description.ilike(pattern),
                    PartsCatalog.subcategory.ilike(pattern),
                    func.lower(cast(PartsCatalog.compatible_with, String)).contains(query.strip().lower()),
                )
            )

        q = q.order_by(PartsCatalog.category, PartsCatalog.name).limit(limit)
        result = await self.db.execute(q)
        return [self._to_dict(p) for p in result.scalars().all()]

    async def get_part(self, part_id: str) -> Optional[dict]:
        """Get single part detail by ID."""
        result = await self.db.execute(
            select(PartsCatalog).where(PartsCatalog.id == part_id)
        )
        part = result.scalar_one_or_none()
        return self._to_dict(part) if part else None

    async def get_categories(self, vendor_provider: Optional[str] = None) -> list[str]:
        """List available categories."""
        q = select(distinct(PartsCatalog.category)).where(PartsCatalog.category.isnot(None))
        if vendor_provider:
            q = q.where(PartsCatalog.vendor_provider == vendor_provider)
        q = q.order_by(PartsCatalog.category)
        result = await self.db.execute(q)
        return [r[0] for r in result.all()]

    async def get_brands(self, vendor_provider: Optional[str] = None) -> list[str]:
        """List available brands."""
        q = select(distinct(PartsCatalog.brand)).where(PartsCatalog.brand.isnot(None))
        if vendor_provider:
            q = q.where(PartsCatalog.vendor_provider == vendor_provider)
        q = q.order_by(PartsCatalog.brand)
        result = await self.db.execute(q)
        return [r[0] for r in result.all()]

    async def get_stats(self) -> dict:
        """Catalog stats — total parts, by vendor."""
        total = await self.db.execute(select(func.count(PartsCatalog.id)))
        by_vendor = await self.db.execute(
            select(PartsCatalog.vendor_provider, func.count(PartsCatalog.id))
            .group_by(PartsCatalog.vendor_provider)
        )
        return {
            "total": total.scalar() or 0,
            "by_vendor": {r[0]: r[1] for r in by_vendor.all()},
        }

    @staticmethod
    def _to_dict(p: PartsCatalog) -> dict:
        return {
            "id": p.id,
            "vendor_provider": p.vendor_provider,
            "sku": p.sku,
            "name": p.name,
            "brand": p.brand,
            "category": p.category,
            "subcategory": p.subcategory,
            "description": p.description,
            "image_url": p.image_url,
            "product_url": p.product_url,
            "specs": p.specs,
            "compatible_with": p.compatible_with,
            "is_chemical": p.is_chemical,
            "last_scraped_at": p.last_scraped_at.isoformat() if p.last_scraped_at else None,
        }
