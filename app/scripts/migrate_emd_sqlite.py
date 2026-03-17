#!/usr/bin/env python3
"""Migrate EMD data from Pool Scout Pro SQLite database to QuantumPools PostgreSQL.

Reads from: /mnt/Projects/archive/pool_scout_pro/data/inspection_data.db
Inserts into: QuantumPools PostgreSQL (emd_facilities, emd_inspections, emd_violations, emd_equipment)

Run from the app/ directory:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/migrate_emd_sqlite.py
"""

import asyncio
import os
import sys
import sqlite3
import uuid
from datetime import datetime, timezone

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SQLITE_DB = "/mnt/Projects/archive/pool_scout_pro/data/inspection_data.db"


async def migrate():
    from src.core.database import get_engine, get_session_maker, Base
    from src.models.emd_facility import EMDFacility
    from src.models.emd_inspection import EMDInspection
    from src.models.emd_violation import EMDViolation
    from src.models.emd_equipment import EMDEquipment

    if not os.path.exists(SQLITE_DB):
        print(f"ERROR: SQLite DB not found at {SQLITE_DB}")
        return

    # Connect to SQLite
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Count records
    cur.execute("SELECT COUNT(*) FROM facilities")
    fac_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inspection_reports")
    report_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM violations")
    viol_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM equipment")
    equip_count = cur.fetchone()[0]

    print(f"Source SQLite: {fac_count} facilities, {report_count} reports, {viol_count} violations, {equip_count} equipment")

    # Get async session
    session_maker = get_session_maker()

    async with session_maker() as session:
        try:
            # Check if EMD tables already have data
            from sqlalchemy import select, func
            existing = (await session.execute(select(func.count(EMDFacility.id)))).scalar()
            if existing > 0:
                print(f"WARNING: emd_facilities already has {existing} records. Skipping migration.")
                print("To re-run, truncate emd_facilities, emd_inspections, emd_violations, emd_equipment first.")
                return

            # Map: sqlite facility.id -> pg facility uuid
            facility_map = {}

            # Map: sqlite report.id -> pg inspection uuid
            inspection_map = {}

            # --- Facilities ---
            print(f"\nMigrating {fac_count} facilities...")
            cur.execute("SELECT * FROM facilities")
            batch = 0
            for row in cur.fetchall():
                row = dict(row)
                pg_id = str(uuid.uuid4())
                facility_map[row["id"]] = pg_id

                def t(val, maxlen):
                    if val is None: return None
                    s = str(val)
                    return s[:maxlen] if len(s) > maxlen else s

                facility = EMDFacility(
                    id=pg_id,
                    name=t(row["name"] or "Unknown", 255),
                    street_address=t(row.get("street_address"), 255),
                    city=t(row.get("city"), 100),
                    state=t(row.get("state") or "CA", 50),
                    zip_code=t(row.get("zip_code"), 20),
                    phone=t(row.get("phone"), 50),
                    facility_id=t(row.get("facility_id"), 50),
                    permit_holder=t(row.get("permit_holder"), 255),
                    facility_type=t(row.get("facility_type"), 50),
                )
                session.add(facility)
                batch += 1
                if batch % 100 == 0:
                    await session.flush()
                    print(f"  ... {batch}/{fac_count} facilities")

            await session.flush()
            print(f"  Migrated {batch} facilities")

            # --- Inspection Reports ---
            print(f"\nMigrating {report_count} inspection reports...")
            cur.execute("SELECT * FROM inspection_reports")
            batch = 0
            for row in cur.fetchall():
                row = dict(row)
                sqlite_facility_id = row["facility_id"]
                pg_facility_id = facility_map.get(sqlite_facility_id)
                if not pg_facility_id:
                    continue

                pg_id = str(uuid.uuid4())
                inspection_map[row["id"]] = pg_id

                # Parse date
                inspection_date = None
                if row.get("inspection_date"):
                    try:
                        inspection_date = datetime.strptime(row["inspection_date"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass

                # Truncate fields that may have garbage data in SQLite
                inspector_name = (row.get("inspector_name") or "")[:100] or None
                inspection_type = (row.get("inspection_type") or "")[:50] or None
                closure_status = (row.get("closure_status") or "")[:50] or None

                inspection = EMDInspection(
                    id=pg_id,
                    facility_id=pg_facility_id,
                    inspection_id=row.get("inspection_id"),
                    inspection_date=inspection_date,
                    inspection_type=inspection_type,
                    inspector_name=inspector_name,
                    total_violations=row.get("total_violations") or 0,
                    major_violations=row.get("major_violations") or 0,
                    pool_capacity_gallons=row.get("pool_capacity_gallons"),
                    flow_rate_gpm=row.get("pool_flow_rate_gpm"),
                    pdf_path=row.get("pdf_path"),
                    report_notes=row.get("report_notes"),
                    closure_status=closure_status,
                )
                session.add(inspection)
                batch += 1
                if batch % 200 == 0:
                    await session.flush()
                    print(f"  ... {batch}/{report_count} reports")

            await session.flush()
            print(f"  Migrated {batch} inspection reports")

            # --- Violations ---
            print(f"\nMigrating {viol_count} violations...")
            cur.execute("SELECT * FROM violations")
            batch = 0
            skipped = 0
            for row in cur.fetchall():
                row = dict(row)
                pg_inspection_id = inspection_map.get(row["report_id"])
                pg_facility_id = facility_map.get(row["facility_id"])
                if not pg_inspection_id or not pg_facility_id:
                    skipped += 1
                    continue

                severity = str(row.get("severity_level")) if row.get("severity_level") is not None else None

                def trunc(val, maxlen):
                    if val is None:
                        return None
                    s = str(val)
                    return s[:maxlen] if len(s) > maxlen else s

                violation = EMDViolation(
                    id=str(uuid.uuid4()),
                    inspection_id=pg_inspection_id,
                    facility_id=pg_facility_id,
                    violation_code=trunc(row.get("violation_code"), 20),
                    violation_title=trunc(row.get("violation_title"), 500),
                    observations=row.get("observations"),
                    corrective_action=row.get("corrective_action"),
                    is_major_violation=bool(row.get("is_major_violation")),
                    severity_level=trunc(severity, 20),
                    shorthand_summary=trunc(row.get("shorthand_summary"), 500),
                )
                session.add(violation)
                batch += 1
                if batch % 500 == 0:
                    await session.flush()
                    print(f"  ... {batch}/{viol_count} violations")

            await session.flush()
            print(f"  Migrated {batch} violations (skipped {skipped} with missing refs)")

            # --- Equipment ---
            print(f"\nMigrating {equip_count} equipment records...")
            cur.execute("SELECT * FROM equipment")
            batch = 0
            skipped = 0
            for row in cur.fetchall():
                row = dict(row)
                pg_inspection_id = inspection_map.get(row["report_id"])
                pg_facility_id = facility_map.get(row["facility_id"])
                if not pg_inspection_id or not pg_facility_id:
                    skipped += 1
                    continue

                hp_val = row.get("filter_pump_1_hp")
                hp_str = str(hp_val) if hp_val is not None else None

                def te(val, maxlen):
                    if val is None: return None
                    s = str(val)
                    return s[:maxlen] if len(s) > maxlen else s

                equipment = EMDEquipment(
                    id=str(uuid.uuid4()),
                    inspection_id=pg_inspection_id,
                    facility_id=pg_facility_id,
                    pool_capacity_gallons=row.get("pool_capacity_gallons"),
                    flow_rate_gpm=row.get("flow_rate_gpm"),
                    filter_pump_1_make=te(row.get("filter_pump_1_make"), 100),
                    filter_pump_1_model=te(row.get("filter_pump_1_model"), 100),
                    filter_pump_1_hp=te(hp_str, 50),
                    filter_1_type=te(row.get("filter_1_type"), 50),
                    filter_1_make=te(row.get("filter_1_make"), 100),
                    filter_1_model=te(row.get("filter_1_model"), 100),
                    sanitizer_1_type=te(row.get("sanitizer_1_type"), 50),
                    sanitizer_1_details=te(row.get("sanitizer_1_details"), 200),
                    main_drain_type=te(row.get("main_drain_type"), 100),
                    main_drain_model=te(row.get("main_drain_model"), 100),
                    main_drain_install_date=te(row.get("main_drain_install_date"), 50),
                    equalizer_model=te(row.get("equalizer_model"), 100),
                    equalizer_install_date=te(row.get("equalizer_install_date"), 50),
                )
                session.add(equipment)
                batch += 1
                if batch % 200 == 0:
                    await session.flush()
                    print(f"  ... {batch}/{equip_count} equipment")

            await session.flush()
            print(f"  Migrated {batch} equipment records (skipped {skipped} with missing refs)")

            await session.commit()
            print("\n=== Migration complete ===")
            print(f"  Facilities: {len(facility_map)}")
            print(f"  Inspections: {len(inspection_map)}")

        except Exception as e:
            await session.rollback()
            print(f"\nERROR: Migration failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
