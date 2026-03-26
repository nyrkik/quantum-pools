"""Charge service — business logic for visit charges and templates."""

import uuid
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models.charge_template import ChargeTemplate
from src.models.visit_charge import VisitCharge
from src.models.org_cost_settings import OrgCostSettings
from src.models.customer import Customer
from src.models.property import Property
from src.models.user import User


class ChargeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Templates ──────────────────────────────────────────────

    async def list_templates(self, org_id: str, active_only: bool = True) -> list[dict]:
        q = select(ChargeTemplate).where(ChargeTemplate.organization_id == org_id)
        if active_only:
            q = q.where(ChargeTemplate.is_active == True)
        q = q.order_by(ChargeTemplate.sort_order)
        result = await self.db.execute(q)
        return [self._template_to_dict(t) for t in result.scalars().all()]

    async def create_template(self, org_id: str, **kwargs) -> dict:
        template = ChargeTemplate(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            name=kwargs["name"],
            default_amount=kwargs["default_amount"],
            category=kwargs.get("category", "other"),
            is_taxable=kwargs.get("is_taxable", True),
            requires_approval=kwargs.get("requires_approval", False),
            is_active=True,
            sort_order=kwargs.get("sort_order", 0),
        )
        self.db.add(template)
        await self.db.flush()
        return self._template_to_dict(template)

    async def update_template(self, org_id: str, template_id: str, **kwargs) -> dict:
        result = await self.db.execute(
            select(ChargeTemplate).where(
                ChargeTemplate.id == template_id,
                ChargeTemplate.organization_id == org_id,
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError("Template not found")

        for key in ("name", "default_amount", "category", "is_taxable", "requires_approval", "sort_order"):
            if key in kwargs:
                setattr(template, key, kwargs[key])
        await self.db.flush()
        return self._template_to_dict(template)

    async def delete_template(self, org_id: str, template_id: str) -> bool:
        """Soft delete — marks template inactive."""
        result = await self.db.execute(
            select(ChargeTemplate).where(
                ChargeTemplate.id == template_id,
                ChargeTemplate.organization_id == org_id,
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            return False
        template.is_active = False
        await self.db.flush()
        return True

    # ── Charges ────────────────────────────────────────────────

    async def create_charge(self, org_id: str, created_by_user_id: str, **kwargs) -> dict:
        amount = kwargs["amount"]
        requires_approval = kwargs.get("requires_approval", True)

        # Look up template if provided
        template_id = kwargs.get("template_id")
        if template_id:
            result = await self.db.execute(
                select(ChargeTemplate).where(
                    ChargeTemplate.id == template_id,
                    ChargeTemplate.organization_id == org_id,
                )
            )
            template = result.scalar_one_or_none()
            if template and template.requires_approval:
                requires_approval = True

        # Load thresholds
        thresholds = await self._get_thresholds(org_id)
        auto_threshold = thresholds.get("auto_approve_threshold", 75.0)

        # Determine status
        if requires_approval and amount >= auto_threshold:
            status = "pending"
        else:
            status = "approved"

        charge = VisitCharge(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            visit_id=kwargs.get("visit_id"),
            property_id=kwargs["property_id"],
            customer_id=kwargs["customer_id"],
            template_id=template_id,
            description=kwargs["description"],
            amount=amount,
            category=kwargs.get("category", "other"),
            is_taxable=kwargs.get("is_taxable", True),
            notes=kwargs.get("notes"),
            status=status,
            requires_approval=requires_approval,
            created_by=created_by_user_id,
        )
        # Auto-approve: set approver info
        if status == "approved":
            charge.approved_by = created_by_user_id
            charge.approved_at = datetime.now(timezone.utc)

        self.db.add(charge)
        await self.db.flush()
        return await self._charge_to_dict(charge)

    async def list_charges(
        self,
        org_id: str,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        q = select(VisitCharge).where(VisitCharge.organization_id == org_id)
        if status:
            q = q.where(VisitCharge.status == status)
        if customer_id:
            q = q.where(VisitCharge.customer_id == customer_id)
        if date_from:
            q = q.where(VisitCharge.created_at >= date_from)
        if date_to:
            q = q.where(VisitCharge.created_at <= date_to)
        q = q.order_by(VisitCharge.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(q)
        charges = result.scalars().all()
        return [await self._charge_to_dict(c) for c in charges]

    async def get_charge(self, org_id: str, charge_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(VisitCharge).where(
                VisitCharge.id == charge_id,
                VisitCharge.organization_id == org_id,
            )
        )
        charge = result.scalar_one_or_none()
        if not charge:
            return None
        return await self._charge_to_dict(charge)

    async def get_pending_count(self, org_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(VisitCharge).where(
                VisitCharge.organization_id == org_id,
                VisitCharge.status == "pending",
            )
        )
        return result.scalar() or 0

    async def update_charge(self, org_id: str, charge_id: str, user_id: str, **kwargs) -> dict:
        result = await self.db.execute(
            select(VisitCharge).where(
                VisitCharge.id == charge_id,
                VisitCharge.organization_id == org_id,
            )
        )
        charge = result.scalar_one_or_none()
        if not charge:
            raise ValueError("Charge not found")
        if charge.status == "invoiced":
            raise ValueError("Cannot modify an invoiced charge")

        for key in ("description", "amount", "category", "is_taxable", "notes"):
            if key in kwargs:
                setattr(charge, key, kwargs[key])
        await self.db.flush()
        return await self._charge_to_dict(charge)

    async def approve_charge(self, org_id: str, charge_id: str, approved_by_user_id: str) -> dict:
        result = await self.db.execute(
            select(VisitCharge).where(
                VisitCharge.id == charge_id,
                VisitCharge.organization_id == org_id,
            )
        )
        charge = result.scalar_one_or_none()
        if not charge:
            raise ValueError("Charge not found")
        if charge.status != "pending":
            raise ValueError(f"Charge is {charge.status}, cannot approve")

        charge.status = "approved"
        charge.approved_by = approved_by_user_id
        charge.approved_at = datetime.now(timezone.utc)
        await self.db.flush()
        return await self._charge_to_dict(charge)

    async def reject_charge(self, org_id: str, charge_id: str, reason: str) -> dict:
        result = await self.db.execute(
            select(VisitCharge).where(
                VisitCharge.id == charge_id,
                VisitCharge.organization_id == org_id,
            )
        )
        charge = result.scalar_one_or_none()
        if not charge:
            raise ValueError("Charge not found")
        if charge.status != "pending":
            raise ValueError(f"Charge is {charge.status}, cannot reject")

        charge.status = "rejected"
        charge.rejected_reason = reason
        await self.db.flush()
        return await self._charge_to_dict(charge)

    async def get_uninvoiced(self, org_id: str, customer_id: str) -> list[dict]:
        result = await self.db.execute(
            select(VisitCharge).where(
                VisitCharge.organization_id == org_id,
                VisitCharge.customer_id == customer_id,
                VisitCharge.status == "approved",
                VisitCharge.invoice_id == None,
            ).order_by(VisitCharge.created_at.asc())
        )
        charges = result.scalars().all()
        return [await self._charge_to_dict(c) for c in charges]

    async def mark_invoiced(self, org_id: str, charge_ids: list[str], invoice_id: str) -> None:
        await self.db.execute(
            update(VisitCharge)
            .where(
                VisitCharge.organization_id == org_id,
                VisitCharge.id.in_(charge_ids),
                VisitCharge.status == "approved",
            )
            .values(status="invoiced", invoice_id=invoice_id)
        )
        await self.db.flush()

    async def set_photo_url(self, org_id: str, charge_id: str, photo_url: str) -> dict:
        result = await self.db.execute(
            select(VisitCharge).where(
                VisitCharge.id == charge_id,
                VisitCharge.organization_id == org_id,
            )
        )
        charge = result.scalar_one_or_none()
        if not charge:
            raise ValueError("Charge not found")
        charge.photo_url = photo_url
        await self.db.flush()
        return await self._charge_to_dict(charge)

    # ── Thresholds ─────────────────────────────────────────────

    async def get_thresholds(self, org_id: str) -> dict:
        return await self._get_thresholds(org_id)

    async def update_thresholds(self, org_id: str, **kwargs) -> dict:
        result = await self.db.execute(
            select(OrgCostSettings).where(OrgCostSettings.organization_id == org_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            raise ValueError("Organization settings not found")

        for key in ("auto_approve_threshold", "separate_invoice_threshold", "require_photo_threshold"):
            if key in kwargs and kwargs[key] is not None:
                setattr(settings, key, kwargs[key])
        await self.db.flush()
        return {
            "auto_approve_threshold": settings.auto_approve_threshold,
            "separate_invoice_threshold": settings.separate_invoice_threshold,
            "require_photo_threshold": settings.require_photo_threshold,
        }

    # ── Private helpers ────────────────────────────────────────

    async def _get_thresholds(self, org_id: str) -> dict:
        result = await self.db.execute(
            select(OrgCostSettings).where(OrgCostSettings.organization_id == org_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            return {
                "auto_approve_threshold": 75.0,
                "separate_invoice_threshold": 200.0,
                "require_photo_threshold": 50.0,
            }
        return {
            "auto_approve_threshold": settings.auto_approve_threshold,
            "separate_invoice_threshold": settings.separate_invoice_threshold,
            "require_photo_threshold": settings.require_photo_threshold,
        }

    def _template_to_dict(self, t: ChargeTemplate) -> dict:
        return {
            "id": t.id,
            "organization_id": t.organization_id,
            "name": t.name,
            "default_amount": t.default_amount,
            "category": t.category,
            "is_taxable": t.is_taxable,
            "requires_approval": t.requires_approval,
            "is_active": t.is_active,
            "sort_order": t.sort_order,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }

    async def _charge_to_dict(self, c: VisitCharge) -> dict:
        # Resolve customer name + property address
        customer_name = None
        property_address = None
        creator_name = None

        cust_result = await self.db.execute(
            select(Customer.first_name, Customer.last_name, Customer.company_name).where(Customer.id == c.customer_id)
        )
        cust = cust_result.first()
        if cust:
            if cust.company_name:
                customer_name = cust.company_name
            else:
                customer_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip()

        prop_result = await self.db.execute(
            select(Property.address, Property.name).where(Property.id == c.property_id)
        )
        prop = prop_result.first()
        if prop:
            property_address = prop.name or prop.address

        user_result = await self.db.execute(
            select(User.first_name, User.last_name).where(User.id == c.created_by)
        )
        user = user_result.first()
        if user:
            creator_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

        return {
            "id": c.id,
            "organization_id": c.organization_id,
            "visit_id": c.visit_id,
            "property_id": c.property_id,
            "customer_id": c.customer_id,
            "template_id": c.template_id,
            "description": c.description,
            "amount": c.amount,
            "category": c.category,
            "is_taxable": c.is_taxable,
            "photo_url": c.photo_url,
            "notes": c.notes,
            "status": c.status,
            "requires_approval": c.requires_approval,
            "approved_by": c.approved_by,
            "approved_at": c.approved_at.isoformat() if c.approved_at else None,
            "rejected_reason": c.rejected_reason,
            "invoice_id": c.invoice_id,
            "created_by": c.created_by,
            "customer_name": customer_name,
            "property_address": property_address,
            "creator_name": creator_name,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
