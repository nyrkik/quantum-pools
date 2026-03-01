"""
Import data from Pool Service Software (PSS) CSV exports into QuantumPools.

Import order: techs (2) → clients→customers (136) → properties (151) → catalog (71) → invoices (~1143)

Key mappings:
  - PSS Client DisplayName → link properties to customers
  - PSS Property Revenue → sum per customer for monthly_rate
  - PSS Property Manager → tech assignment
  - Pool+Spa at same address → single property with has_spa=True
  - Multi-BOW commercial (Pool #1/#2/#3) → separate properties
  - Invoice history → imported as reference (pss_invoice_id stored)

Usage:
  cd app && python -m scripts.import_pss [--dry-run]
"""

import asyncio
import csv
import uuid
import sys
import secrets
from datetime import datetime, timezone, date
from collections import defaultdict
from pathlib import Path

import asyncpg

DATA_DIR = Path(__file__).parent.parent.parent / "data"
NEW_DB = "postgresql://quantumpools:quantumpools@localhost:5434/quantumpools"

# CSV files (dated export)
CLIENTS_CSV = DATA_DIR / "pssclients-2026-02-13.csv"
PROPERTIES_CSV = DATA_DIR / "pss-properties-2026-02-13.csv"
CATALOG_CSV = DATA_DIR / "psscatalog-2026-02-13.csv"
INVOICES_CSV = DATA_DIR / "pssinvoices-all-2026-02-13.csv"
PAYINFO_CSV = DATA_DIR / "pssclientpayinfo-2026-02-13.csv"

# Known techs — PSS Manager field → tech names
TECH_MAP = {
    "Brian Parrotte": {"first": "Brian", "last": "Parrotte", "email": "brian@quantumpools.com", "color": "#3B82F6"},
    "Shane Parrotte": {"first": "Shane", "last": "Parrotte", "email": "shane@quantumpools.com", "color": "#10B981"},
}

DRY_RUN = "--dry-run" in sys.argv


def read_csv(filepath: Path) -> list[dict]:
    """Read CSV file, stripping whitespace from headers and values."""
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            cleaned = {}
            for k, v in row.items():
                key = k.strip() if k else k
                val = v.strip() if v else ""
                cleaned[key] = val
            rows.append(cleaned)
    return rows


def parse_float(val: str, default: float = 0.0) -> float:
    try:
        return float(val.replace(",", "")) if val else default
    except ValueError:
        return default


def parse_int(val: str, default: int = 0) -> int:
    try:
        return int(val.replace(",", "")) if val else default
    except ValueError:
        return default


def parse_date(val: str) -> date | None:
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_bool(val: str) -> bool:
    return val.upper() in ("YES", "TRUE", "1")


async def main():
    print(f"PSS Import {'(DRY RUN)' if DRY_RUN else ''}")
    print(f"Data dir: {DATA_DIR}")
    print()

    # --- Read all CSVs ---
    clients = read_csv(CLIENTS_CSV)
    properties = read_csv(PROPERTIES_CSV)
    catalog = read_csv(CATALOG_CSV)
    invoices = read_csv(INVOICES_CSV)
    payinfo = read_csv(PAYINFO_CSV)

    print(f"Read: {len(clients)} clients, {len(properties)} properties, "
          f"{len(catalog)} catalog items, {len(invoices)} invoices, {len(payinfo)} pay info")

    # --- Build pay info lookup (by client name → autopay status) ---
    autopay_map = {}
    for pi in payinfo:
        client_name = pi.get("Client", "")
        is_autopay = parse_bool(pi.get("Is AutoPay", ""))
        autopay_map[client_name] = is_autopay

    # --- Group properties by client+address for Pool+Spa merge ---
    props_by_client_addr = defaultdict(list)
    for p in properties:
        client = p.get("Client", "")
        addr = p.get("Address", "")
        props_by_client_addr[(client, addr)].append(p)

    # --- Connect to DB ---
    conn = await asyncpg.connect(NEW_DB)

    try:
        org_id = await conn.fetchval("SELECT id FROM organizations LIMIT 1")
        if not org_id:
            print("ERROR: No organization found. Run the app first to create one.")
            return
        print(f"Organization: {org_id}")

        if DRY_RUN:
            print("\n=== DRY RUN — no data will be written ===\n")

        # Check for existing PSS data
        existing_pss = await conn.fetchval(
            "SELECT count(*) FROM customers WHERE organization_id = $1 AND pss_id IS NOT NULL", org_id
        )
        if existing_pss > 0:
            print(f"WARNING: Found {existing_pss} customers with pss_id already set.")
            print("This script should only be run once. Delete existing PSS data first if re-importing.")
            resp = input("Continue anyway? [y/N] ") if not DRY_RUN else "n"
            if resp.lower() != "y":
                print("Aborted.")
                return

        # --- 1. Import Techs ---
        print("\n--- Techs ---")
        tech_name_to_id = {}

        # Check existing techs first
        existing_techs = await conn.fetch(
            "SELECT id, first_name, last_name FROM techs WHERE organization_id = $1", org_id
        )
        for et in existing_techs:
            full = f"{et['first_name']} {et['last_name']}"
            tech_name_to_id[full] = et["id"]
            print(f"  Existing tech: {full} ({et['id'][:8]}..)")

        # Create any missing techs
        for name, info in TECH_MAP.items():
            if name not in tech_name_to_id:
                tech_id = str(uuid.uuid4())
                tech_name_to_id[name] = tech_id
                if not DRY_RUN:
                    await conn.execute("""
                        INSERT INTO techs (id, organization_id, first_name, last_name, email, color,
                            max_stops_per_day, efficiency_factor, is_active, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                        tech_id, org_id, info["first"], info["last"], info["email"], info["color"],
                        20, 1.0, True,
                        datetime.now(timezone.utc), datetime.now(timezone.utc),
                    )
                print(f"  Created tech: {name} ({tech_id[:8]}..)")

        # --- 2. Import Clients → Customers ---
        print("\n--- Customers ---")
        pss_display_to_cust_id = {}  # PSS DisplayName → QP customer_id
        pss_id_to_cust_id = {}      # PSS ID* → QP customer_id
        created_customers = 0

        for c in clients:
            pss_id = c.get("ID*", "")
            first_name = c.get("FirstName", "")
            last_name = c.get("LastName", "")
            display_name = c.get("DisplayName", "")
            company_name = c.get("CompanyName", "")
            email = c.get("Email", "")
            phone = c.get("Phone", "")
            address = c.get("Address", "")
            city = c.get("City", "")
            state = c.get("State", "")
            zipcode = c.get("Zip", "")
            is_active = c.get("Active", "") == "Active"
            client_type = c.get("ClientType", "Residential").lower()
            notes = c.get("Notes", "")

            # For commercial without first/last, use display name
            if not first_name and not last_name:
                parts = display_name.split(" ", 1) if display_name else ["Unknown", ""]
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""

            # AutoPay from payinfo
            autopay = autopay_map.get(display_name, False)

            # Calculate monthly_rate: sum of property revenue for this client
            client_props = [p for p in properties if p.get("Client", "") == display_name]
            monthly_rate = sum(parse_float(p.get("Revenue", "0")) for p in client_props)

            # Payment method from type
            payment_method = None
            autopay_type = c.get("AutoPayType", "")
            if autopay_type:
                payment_method = "credit_card"

            cust_id = str(uuid.uuid4())
            pss_display_to_cust_id[display_name] = cust_id
            pss_id_to_cust_id[pss_id] = cust_id

            if not DRY_RUN:
                await conn.execute("""
                    INSERT INTO customers (id, organization_id, first_name, last_name, company_name,
                        customer_type, email, phone, billing_address, billing_city, billing_state,
                        billing_zip, monthly_rate, payment_method, payment_terms_days, balance,
                        billing_frequency, difficulty_rating, notes, pss_id, autopay_enabled,
                        is_active, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
                """,
                    cust_id, org_id, first_name, last_name,
                    company_name or None,
                    client_type,
                    email or None,
                    phone or None,
                    address or None,
                    city or None,
                    state or None,
                    zipcode or None,
                    monthly_rate,
                    payment_method,
                    30,    # payment_terms_days
                    0.0,   # balance
                    "monthly",
                    1,     # difficulty_rating
                    notes or None,
                    pss_id,
                    autopay,
                    is_active,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                )
            created_customers += 1

        print(f"  Created {created_customers} customers")

        # --- 3. Import Properties ---
        print("\n--- Properties ---")
        created_props = 0
        merged_spa = 0

        # Track which properties we've already handled (for Pool+Spa merging)
        handled_prop_ids = set()

        for (client_name, addr), group in props_by_client_addr.items():
            cust_id = pss_display_to_cust_id.get(client_name)
            if not cust_id:
                print(f"  WARNING: No customer found for property client '{client_name}'")
                continue

            # Check if this is a Pool+Spa merge case
            bow_names = [p.get("BOW Name", "").lower() for p in group]
            is_pool_spa_merge = (
                len(group) == 2
                and any("pool" in b for b in bow_names)
                and any("spa" in b for b in bow_names)
            )

            if is_pool_spa_merge:
                # Merge Pool+Spa into single property with has_spa=True
                pool_prop = next(p for p in group if "pool" in p.get("BOW Name", "").lower())
                spa_prop = next(p for p in group if "spa" in p.get("BOW Name", "").lower())

                prop_id = str(uuid.uuid4())
                pss_id = pool_prop.get("ID*", "")
                city = pool_prop.get("City", "")
                state = pool_prop.get("State", "")
                zipcode = pool_prop.get("Zip", "")
                pool_gallons = parse_int(pool_prop.get("Pool Gallons", "0"))
                surface_type = pool_prop.get("Surface Type", "") or None
                gate_code = pool_prop.get("Gate Code", "") or spa_prop.get("Gate Code", "") or None
                manager = pool_prop.get("Manager", "") or spa_prop.get("Manager", "")
                notes_for_tech = pool_prop.get("Notes for Tech", "") or spa_prop.get("Notes for Tech", "") or None
                revenue = parse_float(pool_prop.get("Revenue", "0")) + parse_float(spa_prop.get("Revenue", "0"))

                if not DRY_RUN:
                    await conn.execute("""
                        INSERT INTO properties (id, organization_id, customer_id, address, city, state,
                            zip_code, pool_gallons, pool_surface, has_spa, has_water_feature, dog_on_property,
                            gate_code, access_instructions,
                            estimated_service_minutes, is_locked_to_day, is_active, pss_id, notes, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
                    """,
                        prop_id, org_id, cust_id,
                        addr, city, state, zipcode,
                        pool_gallons if pool_gallons > 0 else None,
                        surface_type,
                        True,   # has_spa
                        False,  # has_water_feature
                        False,  # dog_on_property
                        gate_code,
                        notes_for_tech,
                        30, False, True, pss_id,
                        f"Merged Pool+Spa from PSS. Pool rev: ${parse_float(pool_prop.get('Revenue', '0'))}, Spa rev: ${parse_float(spa_prop.get('Revenue', '0'))}",
                        datetime.now(timezone.utc), datetime.now(timezone.utc),
                    )

                for p in group:
                    handled_prop_ids.add(p.get("ID*", ""))
                created_props += 1
                merged_spa += 1

            else:
                # Each BOW becomes a separate property
                for p in group:
                    pss_prop_id = p.get("ID*", "")
                    if pss_prop_id in handled_prop_ids:
                        continue

                    prop_id = str(uuid.uuid4())
                    bow_name = p.get("BOW Name", "")
                    city = p.get("City", "")
                    state = p.get("State", "")
                    zipcode = p.get("Zip", "")
                    pool_gallons = parse_int(p.get("Pool Gallons", "0"))
                    surface_type = p.get("Surface Type", "") or None
                    gate_code = p.get("Gate Code", "") or None
                    manager = p.get("Manager", "")
                    notes_for_tech = p.get("Notes for Tech", "") or None
                    has_spa = "spa" in bow_name.lower()

                    # Build property name/notes for multi-BOW
                    prop_notes = None
                    if bow_name and bow_name.lower() != "pool":
                        prop_notes = f"PSS BOW: {bow_name}"

                    # Use BOW name as address suffix for multi-pool sites
                    prop_address = addr
                    if len(group) > 1 and bow_name:
                        prop_address = f"{addr} ({bow_name})"

                    if not DRY_RUN:
                        await conn.execute("""
                            INSERT INTO properties (id, organization_id, customer_id, address, city, state,
                                zip_code, pool_gallons, pool_surface, has_spa, has_water_feature, dog_on_property,
                                gate_code, access_instructions,
                                estimated_service_minutes, is_locked_to_day, is_active, pss_id, notes, created_at, updated_at)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
                        """,
                            prop_id, org_id, cust_id,
                            prop_address, city, state, zipcode,
                            pool_gallons if pool_gallons > 0 else None,
                            surface_type,
                            has_spa,
                            False,  # has_water_feature
                            False,  # dog_on_property
                            gate_code,
                            notes_for_tech,
                            30, False, True, pss_prop_id,
                            prop_notes,
                            datetime.now(timezone.utc), datetime.now(timezone.utc),
                        )

                    handled_prop_ids.add(pss_prop_id)
                    created_props += 1

        print(f"  Created {created_props} properties ({merged_spa} Pool+Spa merged)")

        # --- 4. Import Service Catalog ---
        print("\n--- Service Catalog ---")
        created_services = 0

        for item in catalog:
            name = item.get("Name", "")
            if not name:
                continue

            svc_id = str(uuid.uuid4())
            description = item.get("Description", "") or None
            item_type_raw = item.get("Item Type", "Service").lower()
            item_type = "product" if item_type_raw == "product" else "service"
            unit_price = parse_float(item.get("Unit Price", "0"))
            unit_cost = parse_float(item.get("Unit Cost", "0"))
            is_taxed = parse_bool(item.get("Is Taxed", "NO"))
            item_number = item.get("Item Number", "").strip() or None

            if not DRY_RUN:
                await conn.execute("""
                    INSERT INTO services (id, organization_id, name, description, category, item_type,
                        duration_minutes, price, unit_cost, is_taxed, item_number,
                        is_active, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                    svc_id, org_id, name, description,
                    item_type,  # use item_type as category too
                    item_type,
                    30,  # duration_minutes default
                    unit_price,
                    unit_cost if unit_cost > 0 else None,
                    is_taxed,
                    item_number,
                    True,
                    datetime.now(timezone.utc), datetime.now(timezone.utc),
                )
            created_services += 1

        print(f"  Created {created_services} service catalog items")

        # --- 5. Import Invoices ---
        print("\n--- Invoices ---")
        created_invoices = 0
        skipped_invoices = 0

        # Get current invoice count for numbering
        existing_count = await conn.fetchval(
            "SELECT count(*) FROM invoices WHERE organization_id = $1", org_id
        ) or 0
        invoice_seq = existing_count

        for inv in invoices:
            pss_inv_id = inv.get("Invoice ID", "").strip()
            client_name = inv.get("Client", "").strip()
            subject = inv.get("Subject", "").strip()
            status_raw = inv.get("Status", "").strip()
            issue_date = parse_date(inv.get("Issue Date", ""))
            due_date = parse_date(inv.get("Due Date", ""))
            paid_on = parse_date(inv.get("Paid On", ""))
            paid_amount = parse_float(inv.get("Paid Amount", "0"))
            sub_amount = parse_float(inv.get("Sub Amount", "0"))
            discount = parse_float(inv.get("Discount", "0"))
            tax1_total = parse_float(inv.get("Tax1 Total", "0"))
            total_amount = parse_float(inv.get("Total Amount", "0"))
            balance = parse_float(inv.get("Balance", "0"))
            notes = inv.get("Notes", "").strip() or None
            is_recurring = parse_bool(inv.get("Is Recurring", ""))
            view_date = inv.get("View Date", "").strip()

            # Map PSS status → QP status
            status_map = {
                "Paid": "paid",
                "Sent": "sent",
                "Draft": "draft",
                "Written-off": "written_off",
                "Void": "void",
                "Overdue": "overdue",
            }
            qp_status = status_map.get(status_raw, "draft")

            # Find customer
            cust_id = pss_display_to_cust_id.get(client_name)
            if not cust_id:
                skipped_invoices += 1
                continue

            if not issue_date:
                skipped_invoices += 1
                continue

            if not due_date:
                # Default: 30 days from issue
                from datetime import timedelta
                due_date = issue_date + timedelta(days=30)

            invoice_seq += 1
            invoice_number = f"QP-{invoice_seq:04d}"
            inv_id = str(uuid.uuid4())

            # Determine dates
            sent_at = None
            viewed_at = None
            if qp_status in ("sent", "viewed", "paid", "overdue", "written_off"):
                sent_at = datetime(issue_date.year, issue_date.month, issue_date.day, tzinfo=timezone.utc)
            if view_date:
                vd = parse_date(view_date)
                if vd:
                    viewed_at = datetime(vd.year, vd.month, vd.day, tzinfo=timezone.utc)

            if not DRY_RUN:
                await conn.execute("""
                    INSERT INTO invoices (id, organization_id, customer_id, invoice_number, subject,
                        status, issue_date, due_date, paid_date, subtotal, discount, tax_rate,
                        tax_amount, total, amount_paid, balance, is_recurring, notes,
                        pss_invoice_id, payment_token, sent_at, viewed_at, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
                """,
                    inv_id, org_id, cust_id, invoice_number, subject or None,
                    qp_status,
                    issue_date, due_date, paid_on,
                    sub_amount,
                    discount,
                    0.0,  # tax_rate (PSS stores absolute tax, not rate)
                    tax1_total,
                    total_amount,
                    paid_amount,
                    balance,
                    is_recurring,
                    notes,
                    pss_inv_id,
                    secrets.token_urlsafe(32),
                    sent_at, viewed_at,
                    datetime.now(timezone.utc), datetime.now(timezone.utc),
                )

                # Create a single line item for the invoice (PSS doesn't export line items)
                if sub_amount > 0:
                    li_id = str(uuid.uuid4())
                    await conn.execute("""
                        INSERT INTO invoice_line_items (id, invoice_id, description, quantity,
                            unit_price, amount, is_taxed, sort_order, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    """,
                        li_id, inv_id,
                        subject or "Pool Service",
                        1.0, sub_amount, sub_amount,
                        tax1_total > 0,
                        0,
                        datetime.now(timezone.utc),
                    )

                # Create payment record for paid invoices
                if qp_status == "paid" and paid_amount > 0 and paid_on:
                    pay_id = str(uuid.uuid4())
                    await conn.execute("""
                        INSERT INTO payments (id, organization_id, customer_id, invoice_id,
                            amount, payment_method, payment_date, status, notes,
                            created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                        pay_id, org_id, cust_id, inv_id,
                        paid_amount,
                        "credit_card",  # PSS is card-based
                        paid_on,
                        "completed",
                        "Imported from PSS",
                        datetime.now(timezone.utc), datetime.now(timezone.utc),
                    )

            created_invoices += 1

        print(f"  Created {created_invoices} invoices (skipped {skipped_invoices})")

        # --- Summary ---
        if not DRY_RUN:
            tech_count = await conn.fetchval(
                "SELECT count(*) FROM techs WHERE organization_id = $1", org_id
            )
            cust_count = await conn.fetchval(
                "SELECT count(*) FROM customers WHERE organization_id = $1", org_id
            )
            prop_count = await conn.fetchval(
                "SELECT count(*) FROM properties WHERE organization_id = $1", org_id
            )
            svc_count = await conn.fetchval(
                "SELECT count(*) FROM services WHERE organization_id = $1", org_id
            )
            inv_count = await conn.fetchval(
                "SELECT count(*) FROM invoices WHERE organization_id = $1", org_id
            )
            pay_count = await conn.fetchval(
                "SELECT count(*) FROM payments WHERE organization_id = $1", org_id
            )
            active_custs = await conn.fetchval(
                "SELECT count(*) FROM customers WHERE organization_id = $1 AND is_active = true", org_id
            )
            total_revenue = await conn.fetchval(
                "SELECT coalesce(sum(monthly_rate), 0) FROM customers WHERE organization_id = $1 AND is_active = true", org_id
            )

            print(f"\n{'='*50}")
            print(f"  PSS IMPORT COMPLETE")
            print(f"{'='*50}")
            print(f"  Techs:         {tech_count}")
            print(f"  Customers:     {cust_count} ({active_custs} active)")
            print(f"  Properties:    {prop_count}")
            print(f"  Services:      {svc_count}")
            print(f"  Invoices:      {inv_count}")
            print(f"  Payments:      {pay_count}")
            print(f"  Monthly rev:   ${total_revenue:,.2f}")
            print(f"{'='*50}")
        else:
            print(f"\n=== DRY RUN COMPLETE — no data written ===")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
