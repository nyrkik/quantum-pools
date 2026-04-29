"""Property service-hold CRUD + active-hold predicate.

A property is "held" on a given date if any PropertyHold row covers that
date inclusively. Recurring billing checks this on the billing period
start date — see `BillingService.generate_recurring_invoices`.
"""

from datetime import date

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.models.property import Property
from src.models.property_hold import PropertyHold


class PropertyHoldService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_property(
        self, property_id: str, *, include_past: bool = False
    ) -> list[PropertyHold]:
        """List holds for a property. Default excludes holds that already ended."""
        stmt = select(PropertyHold).where(PropertyHold.property_id == property_id)
        if not include_past:
            stmt = stmt.where(PropertyHold.end_date >= date.today())
        stmt = stmt.order_by(PropertyHold.start_date.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def is_property_held(
        self, property_id: str, on_date: date | None = None
    ) -> bool:
        """True if any hold covers `on_date` (inclusive). Defaults to today."""
        on_date = on_date or date.today()
        stmt = select(PropertyHold.id).where(
            and_(
                PropertyHold.property_id == property_id,
                PropertyHold.start_date <= on_date,
                PropertyHold.end_date >= on_date,
            )
        ).limit(1)
        return (await self.db.execute(stmt)).first() is not None

    async def get_active_hold(
        self, property_id: str, on_date: date | None = None
    ) -> PropertyHold | None:
        on_date = on_date or date.today()
        stmt = select(PropertyHold).where(
            and_(
                PropertyHold.property_id == property_id,
                PropertyHold.start_date <= on_date,
                PropertyHold.end_date >= on_date,
            )
        ).order_by(PropertyHold.start_date.asc()).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        org_id: str,
        property_id: str,
        start_date: date,
        end_date: date,
        reason: str | None = None,
        created_by_user_id: str | None = None,
    ) -> PropertyHold:
        if end_date < start_date:
            raise ValidationError("end_date must be on or after start_date")
        prop = (await self.db.execute(
            select(Property).where(
                Property.id == property_id, Property.organization_id == org_id
            )
        )).scalar_one_or_none()
        if not prop:
            raise NotFoundError(f"Property {property_id} not found")
        hold = PropertyHold(
            organization_id=org_id,
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(hold)
        await self.db.flush()
        return hold

    async def update(
        self,
        hold_id: str,
        *,
        org_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        reason: str | None = None,
    ) -> PropertyHold:
        hold = await self._get(hold_id, org_id)
        if start_date is not None:
            hold.start_date = start_date
        if end_date is not None:
            hold.end_date = end_date
        if reason is not None:
            hold.reason = reason
        if hold.end_date < hold.start_date:
            raise ValidationError("end_date must be on or after start_date")
        await self.db.flush()
        return hold

    async def delete(self, hold_id: str, *, org_id: str) -> None:
        hold = await self._get(hold_id, org_id)
        await self.db.delete(hold)
        await self.db.flush()

    async def _get(self, hold_id: str, org_id: str) -> PropertyHold:
        hold = (await self.db.execute(
            select(PropertyHold).where(
                PropertyHold.id == hold_id,
                PropertyHold.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not hold:
            raise NotFoundError(f"PropertyHold {hold_id} not found")
        return hold
