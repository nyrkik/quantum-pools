"""
Populate display_name for existing customers.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.customer import Customer


async def populate_display_names():
    """Populate display_name for all customers that don't have one."""
    async with AsyncSessionLocal() as db:
        # Get all customers
        result = await db.execute(select(Customer))
        customers = result.scalars().all()

        updated_count = 0
        for customer in customers:
            # Skip if display_name already set
            if customer.display_name:
                continue

            # Generate display_name based on service_type
            if customer.service_type == 'residential':
                # For residential: "Last, First"
                last = customer.last_name or ''
                first = customer.first_name or ''
                customer.display_name = f"{last}, {first}".strip(', ')
            else:
                # For commercial: use name
                customer.display_name = customer.name or 'Unnamed'

            updated_count += 1

        await db.commit()
        print(f"Updated {updated_count} customers with display_name")


if __name__ == "__main__":
    asyncio.run(populate_display_names())
