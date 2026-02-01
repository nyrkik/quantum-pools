"""
Migrate data from old quantum-pools SQL dump into QuantumPools.

Maps:
  old customer -> new Customer + Property (1:1)
  old driver   -> new Tech
  old assigned_driver_id -> property assigned via service_day_pattern

Reads the COPY data blocks from the SQL dump file directly.
"""

import asyncio
import uuid
import sys
from datetime import datetime, timezone

import asyncpg

OLD_DUMP = "/mnt/Projects/quantum-pools/backups/backup_pre_saas.sql"
NEW_DB = "postgresql://quantumpools:quantumpools@localhost:5434/quantumpools"


def parse_copy_block(lines: list[str], table_name: str) -> list[list[str]]:
    """Extract rows from a COPY ... FROM stdin block."""
    rows = []
    in_block = False
    for line in lines:
        if in_block:
            stripped = line.rstrip("\n")
            if stripped == "\\.":
                break
            rows.append(stripped.split("\t"))
        elif f"COPY public.{table_name} " in line:
            in_block = True
    return rows


def parse_val(val: str):
    """Convert \\N to None, otherwise return string."""
    return None if val == "\\N" else val


async def main():
    # Read dump
    with open(OLD_DUMP, "r") as f:
        lines = f.readlines()

    # Parse customers
    customer_rows = parse_copy_block(lines, "customers")
    # Columns (from CREATE TABLE): id, name, address, latitude, longitude, service_type,
    # difficulty, service_day, locked, time_window_start, time_window_end, notes, is_active,
    # created_at, updated_at, service_days_per_week, service_schedule, assigned_driver_id,
    # visit_duration, first_name, last_name, display_name, email, phone, alt_email, alt_phone,
    # invoice_email, management_company, status, service_rate, billing_frequency, rate_notes,
    # payment_method_type, stripe_customer_id, stripe_payment_method_id, payment_last_four, payment_brand

    # Parse drivers
    driver_rows = parse_copy_block(lines, "drivers")
    # Columns: id, name, email, phone, start_location_address, start_latitude, start_longitude,
    # end_location_address, end_latitude, end_longitude, working_hours_start, working_hours_end,
    # max_customers_per_day, is_active, notes, created_at, updated_at, color

    print(f"Parsed {len(customer_rows)} customers, {len(driver_rows)} drivers from dump")

    conn = await asyncpg.connect(NEW_DB)

    try:
        # Get the org ID (should be exactly one org from Phase 0)
        org_id = await conn.fetchval("SELECT id FROM organizations LIMIT 1")
        if not org_id:
            print("ERROR: No organization found. Create one first via the app.")
            return

        print(f"Target organization: {org_id}")

        # Clear existing test data
        await conn.execute("DELETE FROM route_stops")
        await conn.execute("DELETE FROM routes")
        await conn.execute("DELETE FROM properties")
        await conn.execute("DELETE FROM customers")
        await conn.execute("DELETE FROM techs")
        print("Cleared existing data")

        # --- Insert Techs ---
        old_driver_to_tech = {}  # old driver UUID -> new tech UUID
        for row in driver_rows:
            old_id = row[0]
            name = parse_val(row[1]) or "Unknown"
            name_parts = name.strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            tech_id = str(uuid.uuid4())
            old_driver_to_tech[old_id] = tech_id

            await conn.execute("""
                INSERT INTO techs (id, organization_id, first_name, last_name, email, phone,
                    color, start_lat, start_lng, start_address, end_lat, end_lng, end_address,
                    work_start_time, work_end_time, max_stops_per_day, efficiency_factor,
                    is_active, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            """,
                tech_id, org_id, first_name, last_name,
                parse_val(row[2]),  # email
                parse_val(row[3]),  # phone
                parse_val(row[17]) or "#3B82F6",  # color
                float(row[5]) if parse_val(row[5]) else None,  # start_lat
                float(row[6]) if parse_val(row[6]) else None,  # start_lng
                parse_val(row[4]),  # start_address
                float(row[8]) if parse_val(row[8]) else None,  # end_lat
                float(row[9]) if parse_val(row[9]) else None,  # end_lng
                parse_val(row[7]),  # end_address
                None,  # work_start_time (Time type — skip for simplicity)
                None,  # work_end_time
                int(row[12]) if parse_val(row[12]) else 20,  # max_customers_per_day
                1.0,  # efficiency_factor
                parse_val(row[13]) == "t",  # is_active
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )
            print(f"  Tech: {first_name} {last_name} ({tech_id[:8]}..)")

        # --- Insert Customers + Properties ---
        for row in customer_rows:
            old_cust_id = row[0]
            display_name = parse_val(row[21]) or parse_val(row[1]) or "Unknown"
            first_name = parse_val(row[19])
            last_name = parse_val(row[20])
            service_type = parse_val(row[5]) or "residential"

            # Commercial customers often have no first/last name
            if not first_name and not last_name:
                # Use display_name as company_name, synthesize first/last
                first_name = display_name.split(" ")[0] if display_name else "Unknown"
                last_name = " ".join(display_name.split(" ")[1:]) if display_name and " " in display_name else ""

            address = parse_val(row[2]) or ""
            lat = float(row[3]) if parse_val(row[3]) else None
            lng = float(row[4]) if parse_val(row[4]) else None
            difficulty = int(row[6]) if parse_val(row[6]) else 1
            service_day = parse_val(row[7]) or "monday"
            locked = parse_val(row[8]) == "t"
            visit_duration = int(row[18]) if parse_val(row[18]) else 30
            email = parse_val(row[22])
            phone = parse_val(row[23])
            company_name = parse_val(row[1]) if service_type == "commercial" else None
            monthly_rate = float(row[29]) if parse_val(row[29]) else 0.0
            billing_freq = parse_val(row[30]) or "monthly"
            payment_method = parse_val(row[32])
            notes = parse_val(row[11])

            # Create customer
            cust_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO customers (id, organization_id, first_name, last_name, company_name,
                    customer_type, email, phone, difficulty_rating, notes, is_active,
                    monthly_rate, billing_frequency, payment_method, payment_terms_days, balance,
                    created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            """,
                cust_id, org_id, first_name, last_name or "",
                company_name,
                service_type,
                email, phone,
                difficulty, notes,
                True,
                monthly_rate, billing_freq, payment_method,
                30,   # payment_terms_days
                0.0,  # balance
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )

            # Parse address parts
            addr_parts = address.rsplit(",", 3) if address else ["", "", "", ""]
            street = addr_parts[0].strip() if len(addr_parts) > 0 else address
            city = addr_parts[1].strip() if len(addr_parts) > 1 else ""
            state_zip = addr_parts[2].strip() if len(addr_parts) > 2 else ""
            # state_zip might be "CA 95841" or "CA" with zip in next part
            sp = state_zip.split()
            state = sp[0] if sp else "CA"
            zip_code = sp[1] if len(sp) > 1 else (addr_parts[3].strip() if len(addr_parts) > 3 else "")

            # Create property
            prop_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO properties (id, organization_id, customer_id, address, city, state,
                    zip_code, lat, lng, estimated_service_minutes, service_day_pattern,
                    is_locked_to_day, has_spa, has_water_feature, dog_on_property,
                    notes, is_active, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
            """,
                prop_id, org_id, cust_id,
                street, city, state, zip_code,
                lat, lng,
                visit_duration,
                service_day,
                locked,
                False,  # has_spa
                False,  # has_water_feature
                False,  # dog_on_property
                notes,
                True,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )

        print(f"Inserted {len(customer_rows)} customers + properties")

        # Summary
        tech_count = await conn.fetchval("SELECT count(*) FROM techs WHERE organization_id = $1", org_id)
        cust_count = await conn.fetchval("SELECT count(*) FROM customers WHERE organization_id = $1", org_id)
        prop_count = await conn.fetchval("SELECT count(*) FROM properties WHERE organization_id = $1", org_id)
        geo_count = await conn.fetchval("SELECT count(*) FROM properties WHERE organization_id = $1 AND lat IS NOT NULL", org_id)

        print(f"\n=== Migration Complete ===")
        print(f"  Techs:      {tech_count}")
        print(f"  Customers:  {cust_count}")
        print(f"  Properties: {prop_count} ({geo_count} geocoded)")

        # Day breakdown
        days = await conn.fetch("""
            SELECT service_day_pattern, count(*) as cnt
            FROM properties WHERE organization_id = $1
            GROUP BY service_day_pattern ORDER BY cnt DESC
        """, org_id)
        print(f"\n  Properties by day:")
        for d in days:
            print(f"    {d['service_day_pattern']:12s} {d['cnt']}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
