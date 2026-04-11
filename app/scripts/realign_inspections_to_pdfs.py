"""Unified backfill: walk every inspection, re-extract its PDF, and realign
the DB to match the PDF (the canonical source).

Fixes three classes of drift surfaced by the audit:
  1. WRONG_FA — inspection linked to wrong facility row (PDF's FA differs)
  2. WRONG_DATE — DB inspection_date differs from PDF
  3. MULTI_BUILDING — Arbor Ridge / Renaissance pattern: one establishment,
     multiple program_identifiers, currently collapsed into one facility row

Strategy per inspection: re-create the (facility, inspection) link via the
new `process_facility` pipeline, but in "realign" mode where instead of
INSERTing a duplicate, we UPDATE the existing inspection row to point at
the correct facility and update the date/program_identifier from the PDF.

Order of operations per inspection:
  1. Extract PDF: facility_id (FA), program_identifier, inspection_date,
     facility_name, address, etc.
  2. Find or create the right facility row by (FA, program_identifier),
     using the same dedup logic as the live scraper
     (`InspectionService._find_or_create_facility`).
  3. If the inspection already points at this facility row → no-op (most rows)
  4. Otherwise update inspection.facility_id, .inspection_date,
     .program_identifier, also reassign violations and equipment.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/realign_inspections_to_pdfs.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/realign_inspections_to_pdfs.py
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.models.inspection_facility import InspectionFacility
from src.models.inspection_violation import InspectionViolation
from src.models.inspection_equipment import InspectionEquipment
from src.services.inspection.pdf_extractor import EMDPDFExtractor
from src.services.inspection.service import InspectionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def main(dry_run: bool):
    extractor = EMDPDFExtractor()

    async with get_db_context() as db:
        rows = (await db.execute(
            select(
                Inspection.id,
                Inspection.inspection_id,
                Inspection.inspection_date,
                Inspection.program_identifier,
                Inspection.pdf_path,
                Inspection.facility_id,
            ).where(Inspection.pdf_path.isnot(None))
        )).all()

    logger.info(f"Walking {len(rows)} inspections")

    stats = {
        "total": len(rows),
        "no_pdf_data": 0,
        "no_change": 0,
        "facility_changed": 0,
        "date_changed": 0,
        "program_id_changed": 0,
        "facility_created": 0,
        "errors": 0,
    }

    for row_id, iid, db_date, db_prog, pdf_path, db_fac_id in rows:
        if not pdf_path or not Path(pdf_path).exists():
            stats["no_pdf_data"] += 1
            continue

        try:
            data = extractor.extract_all(pdf_path)
        except Exception as e:
            logger.warning(f"  {iid[:8]}: PDF extract failed: {e}")
            stats["errors"] += 1
            continue

        if not data.get("facility_id"):
            stats["no_pdf_data"] += 1
            continue

        # Build the same facility_data dict that process_facility expects
        fdata = {
            "name": data.get("facility_name") or "",
            "facility_id": data["facility_id"],
            "program_identifier": data.get("program_identifier"),
            "permit_holder": data.get("permit_holder"),
            "phone": data.get("phone_number"),
            "street_address": data.get("facility_address"),
            "city": data.get("facility_city"),
            "zip_code": data.get("facility_zip"),
            "facility_type": None,
        }

        async with get_db_context() as db:
            svc = InspectionService(db)
            try:
                target_facility, was_created = await svc._find_or_create_facility(
                    name=fdata["name"], data=fdata,
                )
                if was_created:
                    stats["facility_created"] += 1

                changed = False

                # Reassign inspection if it's pointing at the wrong facility
                if db_fac_id != target_facility.id:
                    stats["facility_changed"] += 1
                    changed = True
                    if not dry_run:
                        await db.execute(
                            update(Inspection)
                            .where(Inspection.id == row_id)
                            .values(facility_id=target_facility.id)
                        )
                        # Move violations + equipment with the inspection's facility_id
                        await db.execute(
                            update(InspectionViolation)
                            .where(InspectionViolation.inspection_id == row_id)
                            .values(facility_id=target_facility.id)
                        )
                        await db.execute(
                            update(InspectionEquipment)
                            .where(InspectionEquipment.inspection_id == row_id)
                            .values(facility_id=target_facility.id)
                        )

                # Date drift
                pdf_date_str = data.get("inspection_date")
                if pdf_date_str:
                    try:
                        pdf_date = datetime.strptime(pdf_date_str, "%Y-%m-%d").date()
                        if db_date != pdf_date:
                            stats["date_changed"] += 1
                            changed = True
                            if not dry_run:
                                await db.execute(
                                    update(Inspection)
                                    .where(Inspection.id == row_id)
                                    .values(inspection_date=pdf_date)
                                )
                    except (ValueError, TypeError):
                        pass

                # program_identifier drift on the inspection row itself
                pdf_prog = data.get("program_identifier")
                if pdf_prog and pdf_prog != db_prog:
                    stats["program_id_changed"] += 1
                    changed = True
                    if not dry_run:
                        await db.execute(
                            update(Inspection)
                            .where(Inspection.id == row_id)
                            .values(program_identifier=pdf_prog)
                        )

                if changed and not dry_run:
                    await db.commit()
                elif not changed:
                    stats["no_change"] += 1
                    # Roll back any flush from _find_or_create_facility's
                    # auto-split path so we don't accidentally create empty rows
                    if was_created:
                        await db.rollback()
                else:
                    # Dry run with changes — roll back
                    await db.rollback()

            except Exception as e:
                import traceback
                logger.warning(f"  {iid[:8]}: {e}")
                if stats["errors"] < 3:
                    logger.warning(traceback.format_exc())
                stats["errors"] += 1
                await db.rollback()

        if (stats["no_change"] + stats["facility_changed"] + stats["date_changed"]) % 200 == 0:
            logger.info(
                f"  progress: no_change={stats['no_change']} "
                f"fac={stats['facility_changed']} date={stats['date_changed']} "
                f"prog={stats['program_id_changed']} created={stats['facility_created']}"
            )

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    if dry_run:
        logger.info("(dry run — nothing committed)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
