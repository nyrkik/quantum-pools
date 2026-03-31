"""Backfill customer_contacts from existing Customer.email field.

Creates a primary contact for each customer that has an email address.
Safe to run multiple times — skips customers that already have contacts.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session_maker
from src.models.customer import Customer
from src.models.customer_contact import CustomerContact


async def backfill():
    session_maker = get_session_maker()
    async with session_maker() as db:
        # Get all customers with email
        result = await db.execute(
            select(Customer).where(Customer.email.isnot(None), Customer.email != "")
        )
        customers = result.scalars().all()

        created = 0
        skipped = 0

        for cust in customers:
            # Check if contacts already exist
            existing = await db.execute(
                select(func.count()).select_from(CustomerContact).where(
                    CustomerContact.customer_id == cust.id
                )
            )
            if existing.scalar() > 0:
                skipped += 1
                continue

            name = f"{cust.first_name} {cust.last_name}".strip()
            now = datetime.now(timezone.utc)

            contact = CustomerContact(
                id=str(uuid.uuid4()),
                customer_id=cust.id,
                organization_id=cust.organization_id,
                name=name,
                email=cust.email,
                phone=cust.phone,
                role="primary",
                receives_estimates=True,
                receives_invoices=True,
                receives_service_updates=True,
                is_primary=True,
                created_at=now,
                updated_at=now,
            )
            db.add(contact)
            created += 1

        await db.commit()
        print(f"Created {created} contacts, skipped {skipped} (already have contacts)")


if __name__ == "__main__":
    asyncio.run(backfill())
