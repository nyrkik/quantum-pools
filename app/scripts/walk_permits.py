"""Permit walker: for each unique permit URL we know about, fetch the
permit page directly and ingest any inspections we're missing.

This catches the multi-BoW collapse: when an establishment has multiple
permits inspected on the same day, the date-search listing only shows one
row, but the permit page lists every inspection for that permit. Walking
permits closes the gap.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/walk_permits.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/walk_permits.py
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/walk_permits.py --matched-only
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.models.inspection_facility import InspectionFacility
from src.services.inspection.scraper import InspectionScraper, PortalBlocked
from src.services.inspection.service import InspectionService
from src.services.inspection.pdf_extractor import EMDPDFExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads" / "emd"
RATE_LIMIT_SECONDS = 8  # MUST match the conservative default in backfill_inspections.py / emd_daily_scraper.py


async def main(dry_run: bool, matched_only: bool):
    extractor = EMDPDFExtractor()

    async with get_db_context() as db:
        # Distinct permit URLs we know about, optionally limited to matched
        # facilities only (smaller scope for fast iteration).
        query = (
            select(Inspection.permit_url, InspectionFacility.id, InspectionFacility.name)
            .join(InspectionFacility, InspectionFacility.id == Inspection.facility_id)
            .where(Inspection.permit_url.isnot(None))
            .distinct()
        )
        if matched_only:
            query = query.where(InspectionFacility.matched_property_id.isnot(None))

        rows = (await db.execute(query)).all()

        # Distinct permit_url -> (facility_id, facility_name)
        permits = {}
        for url, fid, fname in rows:
            permits.setdefault(url, (fid, fname))

    logger.info(
        f"Walking {len(permits)} unique permit URLs"
        + (" (matched facilities only)" if matched_only else "")
    )

    stats = {
        "permits_walked": 0,
        "inspections_seen_on_permits": 0,
        "inspections_already_have": 0,
        "inspections_added": 0,
        "pdfs_downloaded": 0,
        "errors": 0,
    }

    scraper = InspectionScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)
    try:
        for i, (permit_url, (facility_id, facility_name)) in enumerate(permits.items(), 1):
            try:
                listed = await scraper.get_permit_inspections(permit_url)
            except PortalBlocked as e:
                logger.error(f"ABORTING: {e}")
                break
            except Exception as e:
                logger.warning(f"  walk failed for {permit_url}: {e}")
                stats["errors"] += 1
                continue

            stats["permits_walked"] += 1
            stats["inspections_seen_on_permits"] += len(listed)
            if not listed:
                continue

            # Check which we already have
            async with get_db_context() as db:
                existing = (await db.execute(
                    select(Inspection.inspection_id).where(
                        Inspection.inspection_id.in_([l["inspection_id"] for l in listed])
                    )
                )).all()
                have_ids = {r[0] for r in existing}

            new_inspections = [l for l in listed if l["inspection_id"] not in have_ids]
            stats["inspections_already_have"] += len(listed) - len(new_inspections)

            if not new_inspections:
                continue

            logger.info(f"  [{i}/{len(permits)}] {facility_name[:40]}: {len(new_inspections)} new inspections to add")

            for new in new_inspections:
                iid = new["inspection_id"]
                pdf_url = new.get("pdf_url")

                # Download PDF
                pdf_path = None
                if pdf_url:
                    insp_date_str = new.get("inspection_date") or "unknown"
                    try:
                        year_dir = UPLOADS_DIR / (insp_date_str[:4] if insp_date_str != "unknown" else "unknown")
                        year_dir.mkdir(parents=True, exist_ok=True)
                        pdf_path_obj = year_dir / f"{iid}.pdf"
                        if not pdf_path_obj.exists():
                            ok = await scraper.download_pdf(pdf_url, str(pdf_path_obj))
                            if ok and pdf_path_obj.exists() and pdf_path_obj.stat().st_size > 100:
                                stats["pdfs_downloaded"] += 1
                                pdf_path = str(pdf_path_obj)
                            else:
                                logger.warning(f"    PDF download failed for {iid}")
                        else:
                            pdf_path = str(pdf_path_obj)
                            stats["pdfs_downloaded"] += 1
                    except Exception as e:
                        logger.warning(f"    PDF download error for {iid}: {e}")

                if dry_run:
                    stats["inspections_added"] += 1
                    continue

                # Build a facility_data dict for process_facility
                # We already know the facility_id (DB), so this is a known facility — but
                # process_facility expects to look up facility by FA####/name, so we set
                # it up minimally and let _find_or_create_facility handle it via the PDF.
                fdata = {
                    "name": facility_name,
                    "address": "",  # PDF will provide
                    "url": permit_url,
                    "pdf_url": pdf_url,
                    "inspection_id": iid,
                    "inspection_date": new.get("inspection_date"),
                }

                async with get_db_context() as db:
                    svc = InspectionService(db)
                    try:
                        result = await svc.process_facility(fdata, pdf_path=pdf_path)
                        if result in ("new_inspection", "new_facility"):
                            stats["inspections_added"] += 1
                        await db.commit()
                    except Exception as e:
                        logger.warning(f"    process_facility failed for {iid}: {e}")
                        await db.rollback()
                        stats["errors"] += 1

            if i % 25 == 0:
                logger.info(
                    f"  progress: {i}/{len(permits)} permits, "
                    f"{stats['inspections_added']} added, "
                    f"{stats['inspections_already_have']} already had"
                )

    finally:
        await scraper.close()

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    if dry_run:
        logger.info("(dry run — no commits, but PDFs were downloaded)")


if __name__ == "__main__":
    asyncio.run(
        main(
            dry_run="--dry-run" in sys.argv,
            matched_only="--matched-only" in sys.argv,
        )
    )
