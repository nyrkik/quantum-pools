"""Audit every inspection PDF against its DB row.

Walks every PDF in uploads/inspection/, extracts the canonical fields with
EMDPDFExtractor, and compares against the matching `inspections` /
`inspection_facilities` row. Reports any drift. Read-only — no DB writes.

Pass --alert to send a ntfy notification when issues are found (intended
for cron-driven runs). Without --alert it just prints to stdout.

Categories of drift detected:
  1. ORPHAN_PDF       — file on disk has no matching DB row by inspection_id
  2. MISSING_FILE     — DB row points to a pdf_path that doesn't exist
  3. WRONG_DATE       — DB inspection_date != PDF inspection_date
  4. WRONG_FA         — DB facility's facility_id (FA####) != PDF facility_id
  5. WRONG_PERMIT_ID  — DB permit_id != PDF permit_id (PR####)
  6. MULTI_BUILDING   — facility has inspections at multiple program_identifier
                        addresses (one EMD establishment, multiple buildings).
                        This is the Arbor Ridge pattern.
  7. PDF_NO_DATA      — PDF has no extractable data (corrupt or wrong format)

Output:
  - Summary table to stdout
  - CSV file at /tmp/inspection_audit_<ts>.csv with one row per anomaly

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/audit_inspections.py
"""

import argparse
import asyncio
import csv
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.models.inspection_facility import InspectionFacility
from src.services.inspection.pdf_extractor import EMDPDFExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

INSPECTION_ROOT = Path("/srv/quantumpools/app/uploads/inspection")
UUID_RE = re.compile(
    r"^([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})$",
    re.IGNORECASE,
)
# Match the address suffix in program_identifier values like
# "POOL @ 4440 OAK HOLLOW DR" or "SPA @ 4407 OAK HOLLOW DR".
PROG_ADDR_RE = re.compile(r"@\s*(.+?)\s*$")


def collect_pdfs() -> dict[str, Path]:
    """Return {INSPECTION_ID_UPPER: path} for every UUID-named PDF on disk."""
    out: dict[str, Path] = {}
    for p in INSPECTION_ROOT.rglob("*.pdf"):
        m = UUID_RE.match(p.stem)
        if m:
            out[m.group(1).upper()] = p
    return out


def parse_program_address(prog_id: str | None) -> str | None:
    """Extract the building address from a program_identifier like
    'POOL @ 4440 OAK HOLLOW DR'. Returns None if no @ delimiter."""
    if not prog_id:
        return None
    m = PROG_ADDR_RE.search(prog_id)
    return m.group(1).strip().upper() if m else None


async def main(alert: bool = False):
    extractor = EMDPDFExtractor()
    pdfs_on_disk = collect_pdfs()
    logger.info(f"Found {len(pdfs_on_disk)} PDFs on disk")

    async with get_db_context() as db:
        rows = (await db.execute(
            select(
                Inspection.id,
                Inspection.inspection_id,
                Inspection.inspection_date,
                Inspection.permit_id,
                Inspection.program_identifier,
                Inspection.pdf_path,
                Inspection.facility_id,
            ).where(Inspection.inspection_id.isnot(None))
        )).all()
        # Map: inspection_id_upper -> tuple
        db_by_iid = {r[1].upper(): r for r in rows if r[1]}

        # Pre-fetch all facilities for quick lookup
        fac_rows = (await db.execute(
            select(
                InspectionFacility.id,
                InspectionFacility.name,
                InspectionFacility.facility_id,
                InspectionFacility.street_address,
                InspectionFacility.matched_property_id,
            )
        )).all()
        fac_by_id = {r[0]: r for r in fac_rows}

    issues: list[dict] = []
    stats = defaultdict(int)
    # For multi-building detection: facility_id_db -> set of program_addresses
    fac_to_addrs: dict[str, set[str]] = defaultdict(set)
    fac_to_inspections: dict[str, list[tuple[str, str | None]]] = defaultdict(list)

    # 1) Check each PDF on disk
    for iid, pdf_path in pdfs_on_disk.items():
        try:
            data = extractor.extract_all(str(pdf_path))
        except Exception as e:
            issues.append({
                "type": "PDF_EXTRACT_ERROR",
                "inspection_id": iid,
                "pdf_path": str(pdf_path),
                "detail": str(e),
            })
            stats["PDF_EXTRACT_ERROR"] += 1
            continue

        if not data.get("inspection_date") and not data.get("facility_id"):
            issues.append({
                "type": "PDF_NO_DATA",
                "inspection_id": iid,
                "pdf_path": str(pdf_path),
                "detail": "PDF extractor returned no usable fields",
            })
            stats["PDF_NO_DATA"] += 1
            continue

        db_row = db_by_iid.get(iid)
        if not db_row:
            issues.append({
                "type": "ORPHAN_PDF",
                "inspection_id": iid,
                "pdf_path": str(pdf_path),
                "detail": "PDF on disk has no matching DB row",
            })
            stats["ORPHAN_PDF"] += 1
            continue

        (row_id, db_iid, db_date, db_permit, db_prog, db_pdf_path, db_fac_id) = db_row
        pdf_date_str = data.get("inspection_date")
        pdf_fa = (data.get("facility_id") or "").strip()
        pdf_permit = (data.get("permit_id") or "").strip()
        pdf_prog = (data.get("program_identifier") or "").strip()

        # Date drift
        if pdf_date_str:
            try:
                pdf_date = datetime.strptime(pdf_date_str, "%Y-%m-%d").date()
                if db_date != pdf_date:
                    issues.append({
                        "type": "WRONG_DATE",
                        "inspection_id": iid,
                        "db_value": str(db_date),
                        "pdf_value": str(pdf_date),
                    })
                    stats["WRONG_DATE"] += 1
            except (ValueError, TypeError):
                pass

        # FA drift (compare against the linked facility's facility_id)
        fac_row = fac_by_id.get(db_fac_id) if db_fac_id else None
        db_fa = (fac_row[2] or "").strip() if fac_row else ""
        if pdf_fa and db_fa and pdf_fa != db_fa:
            issues.append({
                "type": "WRONG_FA",
                "inspection_id": iid,
                "db_value": db_fa,
                "pdf_value": pdf_fa,
                "facility_name": fac_row[1] if fac_row else "",
            })
            stats["WRONG_FA"] += 1

        # Permit ID drift
        if pdf_permit and db_permit and pdf_permit != db_permit:
            issues.append({
                "type": "WRONG_PERMIT_ID",
                "inspection_id": iid,
                "db_value": db_permit or "",
                "pdf_value": pdf_permit,
            })
            stats["WRONG_PERMIT_ID"] += 1

        # Track multi-building per facility (using PDF's program_identifier
        # rather than the DB's, since the DB value might be stale)
        prog_addr = parse_program_address(pdf_prog)
        if db_fac_id and prog_addr:
            fac_to_addrs[db_fac_id].add(prog_addr)
            fac_to_inspections[db_fac_id].append((iid, prog_addr))

    # 2) Check each DB row for missing files
    db_iids = set(db_by_iid.keys())
    pdf_iids = set(pdfs_on_disk.keys())
    for iid in db_iids - pdf_iids:
        row = db_by_iid[iid]
        issues.append({
            "type": "MISSING_FILE",
            "inspection_id": iid,
            "db_pdf_path": row[5] or "(NULL)",
            "detail": "DB row exists but no PDF on disk under this UUID",
        })
        stats["MISSING_FILE"] += 1

    # 3) Multi-building: any facility with inspections at >1 distinct program address
    multi_building_facilities = {
        fac_id: addrs for fac_id, addrs in fac_to_addrs.items() if len(addrs) > 1
    }
    for fac_id, addrs in multi_building_facilities.items():
        fac_row = fac_by_id.get(fac_id)
        fac_name = fac_row[1] if fac_row else "?"
        fac_fa = fac_row[2] if fac_row else "?"
        for iid, addr in fac_to_inspections[fac_id]:
            issues.append({
                "type": "MULTI_BUILDING",
                "inspection_id": iid,
                "facility_id": fac_id,
                "facility_name": fac_name,
                "fa": fac_fa,
                "building_address": addr,
                "detail": f"FA {fac_fa} has {len(addrs)} buildings: {sorted(addrs)}",
            })
        stats["MULTI_BUILDING"] += 1  # one count per facility, not per inspection

    # Summary
    logger.info("\n=== AUDIT SUMMARY ===")
    logger.info(f"  PDFs on disk:           {len(pdfs_on_disk)}")
    logger.info(f"  DB inspection rows:     {len(db_by_iid)}")
    logger.info(f"  Total issues:           {len(issues)}")
    logger.info("\n=== ISSUES BY TYPE ===")
    for k in sorted(stats.keys()):
        logger.info(f"  {k:25s} {stats[k]}")

    if multi_building_facilities:
        logger.info(f"\n=== MULTI-BUILDING FACILITIES ({len(multi_building_facilities)}) ===")
        for fac_id, addrs in sorted(multi_building_facilities.items(), key=lambda x: -len(x[1])):
            fac_row = fac_by_id.get(fac_id)
            fac_name = fac_row[1] if fac_row else "?"
            fac_fa = fac_row[2] if fac_row else "?"
            insp_count = len(fac_to_inspections[fac_id])
            logger.info(f"  {fac_fa or '(no FA)':12s} {fac_name[:35]:35s} {insp_count} inspections at {len(addrs)} buildings: {sorted(addrs)}")

    # Write CSV
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"/tmp/inspection_audit_{ts}.csv"
    if issues:
        all_keys: set[str] = set()
        for issue in issues:
            all_keys.update(issue.keys())
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sorted(all_keys))
            w.writeheader()
            for issue in issues:
                w.writerow(issue)
        logger.info(f"\nCSV written to: {csv_path}")

    # Push alert if --alert and there are issues other than the unrecoverable
    # PDF_NO_DATA cases (which are a known steady-state edge).
    if alert:
        # PDF_NO_DATA are a known unrecoverable steady-state — don't alert on those alone
        actionable = sum(v for k, v in stats.items() if k != "PDF_NO_DATA")
        if actionable > 0:
            from _notify import alert_failure
            summary_lines = [
                f"{k}: {v}" for k, v in sorted(stats.items()) if v > 0
            ]
            body = (
                f"Inspection audit found {actionable} actionable issue(s):\n"
                + "\n".join(summary_lines)
                + f"\n\nCSV: {csv_path}"
            )
            alert_failure("inspection audit", body, cooldown_seconds=3600)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--alert", action="store_true", help="Send ntfy alert on issues (for cron)")
    args = p.parse_args()
    asyncio.run(main(alert=args.alert))
