"""
Parse and populate first_name, last_name, and display_name from existing customer data.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.customer import Customer


async def parse_customer_names():
    """Parse customer names and populate first_name, last_name, display_name."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Customer))
        customers = result.scalars().all()

        updated_count = 0
        for customer in customers:
            if customer.service_type == 'residential':
                # Parse residential customer name from the original name field
                name = customer.name or ''

                # Always re-parse from name field
                # Try to detect "Last, First" format
                if ',' in name:
                    parts = name.split(',', 1)
                    last = parts[0].strip()
                    first = parts[1].strip() if len(parts) > 1 else ''
                else:
                    # Try to split by space - assume "Last First" format
                    parts = name.strip().split(None, 1)
                    if len(parts) == 2:
                        last = parts[0]  # First word is last name
                        first = parts[1]  # Second word is first name
                    elif len(parts) == 1:
                        # Only one name - treat as last name
                        last = parts[0]
                        first = ''
                    else:
                        last = ''
                        first = ''

                customer.first_name = first
                customer.last_name = last

                # Generate display_name
                if last and first:
                    customer.display_name = f"{last}, {first}"
                elif last:
                    customer.display_name = last
                elif first:
                    customer.display_name = first
                else:
                    customer.display_name = 'Unnamed'

            else:
                # Commercial customer
                customer.display_name = customer.name or 'Unnamed'

            updated_count += 1

        await db.commit()
        print(f"Updated {updated_count} customers")


if __name__ == "__main__":
    asyncio.run(parse_customer_names())
