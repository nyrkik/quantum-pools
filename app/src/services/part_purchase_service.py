"""Part purchase service — business logic for logging and querying purchases."""

import uuid
from datetime import datetime, date, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.part_purchase import PartPurchase
from src.models.org_cost_settings import OrgCostSettings


class PartPurchaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_purchase(self, org_id: str, user_id: str, **kwargs) -> dict:
        unit_cost = kwargs["unit_cost"]
        quantity = kwargs.get("quantity", 1)
        total_cost = round(unit_cost * quantity, 2)

        markup_pct = kwargs.get("markup_pct")
        if markup_pct is None:
            markup_pct = await self._get_default_markup(org_id)

        customer_price = None
        if markup_pct is not None:
            customer_price = round(total_cost * (1 + markup_pct / 100), 2)

        purchased_at = kwargs.get("purchased_at")
        if isinstance(purchased_at, str):
            purchased_at = date.fromisoformat(purchased_at)
        elif purchased_at is None:
            purchased_at = date.today()

        purchase = PartPurchase(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            catalog_part_id=kwargs.get("catalog_part_id"),
            sku=kwargs.get("sku"),
            description=kwargs["description"],
            vendor_name=kwargs["vendor_name"],
            unit_cost=unit_cost,
            quantity=quantity,
            total_cost=total_cost,
            markup_pct=markup_pct,
            customer_price=customer_price,
            visit_charge_id=kwargs.get("visit_charge_id"),
            job_id=kwargs.get("job_id"),
            property_id=kwargs.get("property_id"),
            water_feature_id=kwargs.get("water_feature_id"),
            purchased_by=user_id,
            purchased_at=purchased_at,
            receipt_url=kwargs.get("receipt_url"),
            notes=kwargs.get("notes"),
        )
        self.db.add(purchase)
        await self.db.flush()
        return self._to_dict(purchase)

    async def list_purchases(
        self, org_id: str, *,
        property_id: Optional[str] = None,
        job_id: Optional[str] = None,
        vendor_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        q = select(PartPurchase).where(PartPurchase.organization_id == org_id)
        if property_id:
            q = q.where(PartPurchase.property_id == property_id)
        if job_id:
            q = q.where(PartPurchase.job_id == job_id)
        if vendor_name:
            q = q.where(PartPurchase.vendor_name == vendor_name)
        if date_from:
            q = q.where(PartPurchase.purchased_at >= date.fromisoformat(date_from))
        if date_to:
            q = q.where(PartPurchase.purchased_at <= date.fromisoformat(date_to))
        q = q.order_by(PartPurchase.purchased_at.desc()).limit(limit)
        result = await self.db.execute(q)
        return [self._to_dict(p) for p in result.scalars().all()]

    async def get_job_parts(self, org_id: str, job_id: str) -> list[dict]:
        q = (
            select(PartPurchase)
            .where(PartPurchase.organization_id == org_id, PartPurchase.job_id == job_id)
            .order_by(PartPurchase.purchased_at.desc())
        )
        result = await self.db.execute(q)
        return [self._to_dict(p) for p in result.scalars().all()]

    async def delete_purchase(self, org_id: str, purchase_id: str) -> bool:
        result = await self.db.execute(
            select(PartPurchase).where(
                PartPurchase.id == purchase_id,
                PartPurchase.organization_id == org_id,
            )
        )
        purchase = result.scalar_one_or_none()
        if not purchase:
            return False
        await self.db.delete(purchase)
        await self.db.flush()
        return True

    async def get_purchase_summary(self, org_id: str, months: int = 3) -> dict:
        """Cost summary by vendor over recent months."""
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=months * 30)
        q = (
            select(
                PartPurchase.vendor_name,
                func.count(PartPurchase.id).label("count"),
                func.sum(PartPurchase.total_cost).label("total"),
            )
            .where(
                PartPurchase.organization_id == org_id,
                PartPurchase.purchased_at >= cutoff,
            )
            .group_by(PartPurchase.vendor_name)
            .order_by(func.sum(PartPurchase.total_cost).desc())
        )
        result = await self.db.execute(q)
        rows = result.all()
        return {
            "months": months,
            "by_vendor": [
                {"vendor_name": r.vendor_name, "count": r.count, "total": round(float(r.total or 0), 2)}
                for r in rows
            ],
            "grand_total": round(sum(float(r.total or 0) for r in rows), 2),
        }

    async def get_markup(self, org_id: str) -> float:
        markup = await self._get_default_markup(org_id)
        return markup if markup is not None else 25.0

    async def _get_default_markup(self, org_id: str) -> Optional[float]:
        result = await self.db.execute(
            select(OrgCostSettings.default_parts_markup_pct)
            .where(OrgCostSettings.organization_id == org_id)
        )
        row = result.scalar_one_or_none()
        return row

    @staticmethod
    def _to_dict(p: PartPurchase) -> dict:
        return {
            "id": p.id,
            "organization_id": p.organization_id,
            "catalog_part_id": p.catalog_part_id,
            "sku": p.sku,
            "description": p.description,
            "vendor_name": p.vendor_name,
            "unit_cost": p.unit_cost,
            "quantity": p.quantity,
            "total_cost": p.total_cost,
            "markup_pct": p.markup_pct,
            "customer_price": p.customer_price,
            "visit_charge_id": p.visit_charge_id,
            "job_id": p.job_id,
            "property_id": p.property_id,
            "water_feature_id": p.water_feature_id,
            "purchased_by": p.purchased_by,
            "purchased_at": p.purchased_at.isoformat() if p.purchased_at else None,
            "receipt_url": p.receipt_url,
            "notes": p.notes,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
