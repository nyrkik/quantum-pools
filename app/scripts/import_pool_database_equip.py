#!/usr/bin/env python3
"""Import equipment data from Pool Database.xlsx into BOWs.

Source: Pool Database.xlsx → Active Clients sheet
Maps: Pump, Filter, Chem Feeder, PoolRX, SqFt, Spa gallons, Rate

Matching: by customer display_name (fuzzy match on name).
Only updates fields that are currently NULL on the BOW — never overwrites existing data.
"""

import asyncio
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openpyxl
from sqlalchemy import select, text
from src.core.database import get_db_context
from src.models.body_of_water import BodyOfWater
from src.models.property import Property
from src.models.customer import Customer


def normalize(name: str) -> str:
    """Normalize name for fuzzy matching."""
    if not name:
        return ""
    s = name.lower().strip()
    # Remove common suffixes
    for suffix in ["apartments", "apartment", "apts", "apt", "living", "communities"]:
        s = re.sub(rf"\b{suffix}\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def main():
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/Pool Database.xlsx"
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Active Clients"]

    # Read all rows from spreadsheet
    rows = []
    for row in ws.iter_rows(min_row=2, max_row=200, values_only=True):
        client = row[0]
        if not client:
            continue
        rows.append({
            "client": str(client).strip(),
            "spa_gal": int(row[4]) if row[4] else None,
            "gal": int(row[5]) if row[5] else None,
            "rate": float(row[6]) if row[6] else None,
            "pump": str(row[22]).strip() if row[22] else None,
            "filter": str(row[23]).strip() if row[23] else None,
            "chem_feeder": str(row[24]).strip() if row[24] else None,
            "poolrx": str(row[25]).strip() if row[25] else None,
            "sqft": float(row[31]) if row[31] else None,
        })

    print(f"Read {len(rows)} rows from spreadsheet")

    async with get_db_context() as db:
        # Load all customers with their BOWs
        result = await db.execute(
            select(Customer, Property, BodyOfWater)
            .join(Property, Property.customer_id == Customer.id)
            .join(BodyOfWater, BodyOfWater.property_id == Property.id)
            .where(Customer.is_active == True, BodyOfWater.is_active == True)
            .order_by(Customer.first_name, BodyOfWater.water_type)
        )
        db_rows = result.all()

        # Build lookup: normalized name → list of (customer, property, bow)
        db_lookup = {}
        for cust, prop, bow in db_rows:
            name = normalize(cust.display_name or f"{cust.first_name} {cust.last_name}")
            if name not in db_lookup:
                db_lookup[name] = []
            db_lookup[name].append((cust, prop, bow))

        matched = 0
        updated_fields = 0
        unmatched = []

        for row in rows:
            xlsx_name = normalize(row["client"])

            # Try exact match first, then fuzzy
            matches = db_lookup.get(xlsx_name)
            if not matches:
                # Try partial match
                for db_name, entries in db_lookup.items():
                    if xlsx_name in db_name or db_name in xlsx_name:
                        matches = entries
                        break

            if not matches:
                unmatched.append(row["client"])
                continue

            matched += 1
            # Find the pool BOW (not spa)
            pool_bows = [e for e in matches if e[2].water_type == "pool"]
            spa_bows = [e for e in matches if e[2].water_type == "spa"]

            for cust, prop, bow in pool_bows:
                changes = []

                if row["pump"] and not bow.pump_type:
                    bow.pump_type = row["pump"]
                    changes.append(f"pump={row['pump'][:30]}")

                if row["filter"] and not bow.filter_type:
                    bow.filter_type = row["filter"]
                    changes.append(f"filter={row['filter']}")

                if row["chem_feeder"] and not bow.chlorinator_type:
                    bow.chlorinator_type = row["chem_feeder"]
                    changes.append(f"chem_feeder={row['chem_feeder']}")

                if row["rate"] and not bow.monthly_rate:
                    bow.monthly_rate = row["rate"]
                    changes.append(f"rate={row['rate']}")

                if row["gal"] and not bow.pool_gallons:
                    bow.pool_gallons = int(row["gal"])
                    changes.append(f"gal={row['gal']}")

                if row["sqft"] and not bow.pool_sqft:
                    bow.pool_sqft = row["sqft"]
                    changes.append(f"sqft={row['sqft']}")

                if changes:
                    updated_fields += len(changes)
                    print(f"  {cust.display_name} (pool): {', '.join(changes)}")

            # Update spa gallons
            if row["spa_gal"] and spa_bows:
                for cust, prop, bow in spa_bows:
                    if not bow.pool_gallons:
                        bow.pool_gallons = row["spa_gal"]
                        updated_fields += 1
                        print(f"  {cust.display_name} (spa): gal={row['spa_gal']}")

        await db.commit()

        print(f"\nMatched: {matched}/{len(rows)}")
        print(f"Updated fields: {updated_fields}")
        if unmatched:
            print(f"\nUnmatched ({len(unmatched)}):")
            for name in unmatched:
                print(f"  {name}")


if __name__ == "__main__":
    asyncio.run(main())
