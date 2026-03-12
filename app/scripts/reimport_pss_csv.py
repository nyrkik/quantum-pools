"""
Reimport customers/properties from PSS CSV export.

Only imports Active clients. Clears existing customers, properties, and all
dependent data (invoices, payments, satellite analyses, etc).
Preserves techs.

Usage:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/reimport_pss_csv.py /tmp/pssclients.csv
"""

import asyncio
import csv
import sys
import uuid
from datetime import datetime, timezone

import asyncpg

DB_URL = "postgresql://quantumpools:quantumpools@localhost:7062/quantumpools"


def parse_csv(path: str) -> list[dict]:
    """Parse PSS CSV, stripping leading spaces from headers."""
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Strip whitespace from field names
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        rows = []
        for row in reader:
            cleaned = {k.strip(): v.strip() if v else "" for k, v in row.items()}
            rows.append(cleaned)
    return rows


async def main():
    if len(sys.argv) < 2:
        print("Usage: python reimport_pss_csv.py <csv_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    all_rows = parse_csv(csv_path)
    active_rows = [r for r in all_rows if r.get("Active", "").lower() == "active"]

    print(f"CSV: {len(all_rows)} total, {len(active_rows)} active")

    conn = await asyncpg.connect(DB_URL)

    try:
        org_id = await conn.fetchval("SELECT id FROM organizations LIMIT 1")
        if not org_id:
            print("ERROR: No organization found.")
            return

        print(f"Organization: {org_id}")

        # Clear dependent tables in FK order
        for table in [
            "satellite_analyses",
            "chemical_readings",
            "visit_services",
            "visits",
            "invoice_line_items",
            "invoices",
            "payments",
            "property_difficulties",
            "property_jurisdictions",
            "route_stops",
            "temp_tech_assignments",
            "portal_users",
            "service_requests",
            "properties",
            "customers",
        ]:
            try:
                deleted = await conn.fetchval(f"DELETE FROM {table} WHERE organization_id = $1 RETURNING count(*)", org_id)
            except Exception:
                # Some tables may not have organization_id, or may not exist
                try:
                    # Try without org filter for junction tables
                    await conn.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            print(f"  Cleared {table}")

        print(f"\nImporting {len(active_rows)} active clients...")

        imported = 0
        for row in active_rows:
            pss_id = row.get("ID*", "")
            first_name = row.get("FirstName", "")
            last_name = row.get("LastName", "")
            display_name = row.get("DisplayName", "")
            email = row.get("Email", "") or None
            phone = row.get("Phone", "") or None
            mobile = row.get("Mobile", "") or None
            address = row.get("Address", "")
            city = row.get("City", "")
            state = row.get("State", "CA")
            zipcode = row.get("Zip", "")
            company_name = row.get("CompanyName", "") or None
            client_type = row.get("ClientType", "Residential").lower()
            autopay = row.get("AutoPay", "NO").upper() == "YES"
            notes = row.get("Notes", "") or None

            # Normalize state
            if state.lower() == "california":
                state = "CA"

            # For commercial: use DisplayName or CompanyName as the name
            if client_type == "commercial":
                if not first_name:
                    first_name = display_name or company_name or "Unknown"
                    last_name = ""
            else:
                if not first_name and not last_name:
                    parts = display_name.split(",", 1) if display_name else ["Unknown"]
                    if len(parts) == 2:
                        last_name = parts[0].strip()
                        first_name = parts[1].strip()
                    else:
                        first_name = display_name or "Unknown"
                        last_name = ""

            # Use phone or mobile
            if not phone and mobile:
                phone = mobile

            cust_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO customers (id, organization_id, first_name, last_name, company_name,
                    customer_type, email, phone, difficulty_rating, notes, is_active,
                    monthly_rate, billing_frequency, payment_method, payment_terms_days, balance,
                    pss_id, autopay_enabled,
                    created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            """,
                cust_id, org_id, first_name, last_name or "",
                company_name,
                client_type,
                email, phone,
                1,      # difficulty_rating default
                notes,
                True,   # is_active
                0.0,    # monthly_rate (not in CSV)
                "monthly",
                None,   # payment_method
                30,     # payment_terms_days
                0.0,    # balance
                pss_id,
                autopay,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )

            # Create property from address
            prop_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO properties (id, organization_id, customer_id, address, city, state,
                    zip_code, estimated_service_minutes, is_locked_to_day,
                    has_spa, has_water_feature, dog_on_property,
                    notes, is_active, pss_id,
                    created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            """,
                prop_id, org_id, cust_id,
                address, city, state, zipcode,
                30,     # estimated_service_minutes
                False,  # is_locked_to_day
                False,  # has_spa
                False,  # has_water_feature
                False,  # dog_on_property
                notes,
                True,   # is_active
                pss_id,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )

            imported += 1
            ctype_label = "COM" if client_type == "commercial" else "RES"
            name_label = f"{first_name} {last_name}".strip() if last_name else first_name
            print(f"  [{ctype_label}] {name_label} — {address}, {city}")

        print(f"\n=== Import Complete ===")

        # Summary
        cust_count = await conn.fetchval("SELECT count(*) FROM customers WHERE organization_id = $1", org_id)
        prop_count = await conn.fetchval("SELECT count(*) FROM properties WHERE organization_id = $1", org_id)
        com_count = await conn.fetchval("SELECT count(*) FROM customers WHERE organization_id = $1 AND customer_type = 'commercial'", org_id)
        res_count = await conn.fetchval("SELECT count(*) FROM customers WHERE organization_id = $1 AND customer_type = 'residential'", org_id)

        print(f"  Customers:  {cust_count} ({com_count} commercial, {res_count} residential)")
        print(f"  Properties: {prop_count}")
        print(f"\nNext steps: geocode properties, then run satellite analysis")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
