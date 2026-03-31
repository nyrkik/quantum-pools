"""Customer contacts CRUD — multiple contacts per customer with roles and communication preferences."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.models.customer_contact import CustomerContact
from src.models.customer import Customer
from src.schemas.customer_contact import ContactCreate, ContactUpdate

router = APIRouter(prefix="/customers/{customer_id}/contacts", tags=["customer-contacts"])


def _serialize(c: CustomerContact) -> dict:
    return {
        "id": c.id,
        "customer_id": c.customer_id,
        "name": c.name,
        "title": c.title,
        "email": c.email,
        "phone": c.phone,
        "role": c.role,
        "receives_estimates": c.receives_estimates,
        "receives_invoices": c.receives_invoices,
        "receives_service_updates": c.receives_service_updates,
        "is_primary": c.is_primary,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _verify_customer(db: AsyncSession, org_id: str, customer_id: str) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("")
async def list_contacts(
    customer_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_customer(db, ctx.organization_id, customer_id)
    result = await db.execute(
        select(CustomerContact)
        .where(
            CustomerContact.customer_id == customer_id,
            CustomerContact.organization_id == ctx.organization_id,
        )
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.name)
    )
    contacts = result.scalars().all()
    return [_serialize(c) for c in contacts]


@router.post("", status_code=201)
async def create_contact(
    customer_id: str,
    body: ContactCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_customer(db, ctx.organization_id, customer_id)

    # If setting as primary, unset any existing primary
    if body.is_primary:
        await _clear_primary(db, ctx.organization_id, customer_id)

    contact = CustomerContact(
        id=str(uuid.uuid4()),
        customer_id=customer_id,
        organization_id=ctx.organization_id,
        name=body.name,
        title=body.title,
        email=body.email,
        phone=body.phone,
        role=body.role,
        receives_estimates=body.receives_estimates,
        receives_invoices=body.receives_invoices,
        receives_service_updates=body.receives_service_updates,
        is_primary=body.is_primary,
        notes=body.notes,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return _serialize(contact)


@router.put("/{contact_id}")
async def update_contact(
    customer_id: str,
    contact_id: str,
    body: ContactUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CustomerContact).where(
            CustomerContact.id == contact_id,
            CustomerContact.customer_id == customer_id,
            CustomerContact.organization_id == ctx.organization_id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    data = body.model_dump(exclude_unset=True)

    # If setting as primary, unset any existing primary
    if data.get("is_primary"):
        await _clear_primary(db, ctx.organization_id, customer_id, exclude_id=contact_id)

    for key, value in data.items():
        setattr(contact, key, value)

    await db.commit()
    await db.refresh(contact)
    return _serialize(contact)


@router.delete("/{contact_id}")
async def delete_contact(
    customer_id: str,
    contact_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CustomerContact).where(
            CustomerContact.id == contact_id,
            CustomerContact.customer_id == customer_id,
            CustomerContact.organization_id == ctx.organization_id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"ok": True}


async def _clear_primary(db: AsyncSession, org_id: str, customer_id: str, exclude_id: str | None = None):
    """Unset is_primary on all contacts for this customer (except exclude_id)."""
    stmt = select(CustomerContact).where(
        CustomerContact.customer_id == customer_id,
        CustomerContact.organization_id == org_id,
        CustomerContact.is_primary == True,
    )
    if exclude_id:
        stmt = stmt.where(CustomerContact.id != exclude_id)
    result = await db.execute(stmt)
    for c in result.scalars().all():
        c.is_primary = False
