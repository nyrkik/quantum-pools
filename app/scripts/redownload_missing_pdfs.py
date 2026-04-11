"""Redownload PDFs for the 28 inspection records whose pdf_path is NULL or
points to a legacy /mnt/nas/... path that no longer exists.

Uses the existing InspectionScraper.download_pdf path, which goes through
_request — so it inherits the rate limit, the circuit breaker, and the
PortalBlocked exception. Aborts cleanly if the portal returns 403/429.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/redownload_missing_pdfs.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/redownload_missing_pdfs.py
"""

import argparse
import asyncio
import logging
import sys
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update, or_

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.services.inspection.scraper import InspectionScraper, PortalBlocked

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

INSPECTION_ROOT = Path("/srv/quantumpools/app/uploads/inspection")
RATE_LIMIT_SECONDS = 8


async def main(dry_run: bool):
    async with get_db_context() as db:
        rows = (await db.execute(
            select(Inspection.id, Inspection.inspection_id, Inspection.inspection_date, Inspection.pdf_path)
            .where(Inspection.inspection_id.isnot(None))
            .where(or_(
                Inspection.pdf_path.is_(None),
                Inspection.pdf_path.like("/mnt/nas/%"),
            ))
        )).all()

    logger.info(f"Found {len(rows)} records needing redownload")

    stats = {"attempted": 0, "downloaded": 0, "skipped_no_date": 0, "failed": 0}

    scraper = InspectionScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)
    try:
        for row_id, iid, insp_date, current_path in rows:
            # Determine year directory: prefer inspection_date.year, else
            # fall back to "unknown"
            if insp_date:
                year_dir = str(insp_date.year)
            else:
                year_dir = "unknown"
                stats["skipped_no_date"] += 1
                logger.info(f"  {iid[:8]}: NULL inspection_date, will save to inspection/unknown/")

            dest = INSPECTION_ROOT / year_dir / f"{iid}.pdf"
            if dest.exists():
                # Already on disk — just update DB
                logger.info(f"  {iid[:8]}: already on disk, updating DB")
                if not dry_run:
                    async with get_db_context() as db:
                        await db.execute(update(Inspection).where(Inspection.id == row_id).values(pdf_path=str(dest)))
                        await db.commit()
                continue

            # Download via the scraper (the inspection-page URL is what download_pdf wants)
            inspection_page_url = f"/sacramento/program-rec-health/inspection/?inspectionID={iid}"
            stats["attempted"] += 1

            if dry_run:
                logger.info(f"  {iid[:8]}: would download to {dest}")
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                ok = await scraper.download_pdf(inspection_page_url, str(dest))
            except PortalBlocked as e:
                logger.error(f"ABORTING: {e}")
                break
            except Exception as e:
                logger.warning(f"  {iid[:8]}: download error: {e}")
                stats["failed"] += 1
                continue

            if ok and dest.exists() and dest.stat().st_size > 100:
                stats["downloaded"] += 1
                logger.info(f"  {iid[:8]}: downloaded ({dest.stat().st_size} bytes)")
                async with get_db_context() as db:
                    await db.execute(update(Inspection).where(Inspection.id == row_id).values(pdf_path=str(dest)))
                    await db.commit()
            else:
                stats["failed"] += 1
                logger.warning(f"  {iid[:8]}: download failed")
    finally:
        await scraper.close()

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    if dry_run:
        logger.info("(dry run — nothing downloaded)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
