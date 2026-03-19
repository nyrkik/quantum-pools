#!/usr/bin/env python3
"""Download missing EMD inspection PDFs.

Finds all inspections that either have no PDF or have a stale NAS path,
constructs the EMD portal URL from the inspection_id, and downloads.

Rate-limited to avoid getting blocked.

Usage:
    nohup python scripts/emd_pdf_download_missing.py > /tmp/emd_pdf_download.log 2>&1 &
    # Monitor:
    tail -f /tmp/emd_pdf_download.log
"""

import asyncio
import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "emd")
PAUSE_BETWEEN_DOWNLOADS = 8  # seconds
EMD_INSPECTION_URL_TEMPLATE = "/sacramento/program-rec-health/inspection/?inspectionID={inspection_id}"


async def main():
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from src.services.emd.pdf_extractor import EMDPDFExtractor
    from src.models.emd_inspection import EMDInspection
    from sqlalchemy import select, or_

    scraper = EMDScraper(rate_limit_seconds=PAUSE_BETWEEN_DOWNLOADS)
    extractor = EMDPDFExtractor()

    downloaded = 0
    failed = 0
    already_exists = 0
    re_extracted = 0

    try:
        async with get_db_context() as db:
            # Find inspections needing PDF download
            result = await db.execute(
                select(EMDInspection)
                .where(
                    EMDInspection.inspection_id.isnot(None),
                    or_(
                        EMDInspection.pdf_path.is_(None),
                        EMDInspection.pdf_path.like("/mnt%"),
                    ),
                    EMDInspection.pdf_permanently_missing == False,
                )
                .order_by(EMDInspection.inspection_date.desc())
            )
            inspections = result.scalars().all()
            logger.info(f"Inspections needing PDF: {len(inspections)}")

            for i, insp in enumerate(inspections):
                # Determine save path
                year = str(insp.inspection_date.year) if insp.inspection_date else "unknown"
                year_dir = os.path.join(UPLOADS_DIR, year)
                os.makedirs(year_dir, exist_ok=True)
                pdf_path = os.path.join(year_dir, f"{insp.inspection_id}.pdf")

                # Check if already on disk (from a previous partial run)
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
                    insp.pdf_path = pdf_path
                    already_exists += 1
                    # Re-extract data
                    data = extractor.extract_all(pdf_path)
                    if data.get("permit_id"):
                        insp.permit_id = data["permit_id"]
                    if data.get("program_identifier"):
                        insp.program_identifier = data["program_identifier"]
                    re_extracted += 1
                    if (i + 1) % 50 == 0:
                        await db.flush()
                        logger.info(f"  [{i+1}/{len(inspections)}] {already_exists} already on disk, {downloaded} downloaded, {failed} failed")
                    continue

                # Construct URL and download
                inspection_url = EMD_INSPECTION_URL_TEMPLATE.format(inspection_id=insp.inspection_id)
                logger.info(f"  [{i+1}/{len(inspections)}] Downloading {insp.inspection_id} ({insp.inspection_date})...")

                success = await scraper.download_pdf(inspection_url, pdf_path)
                if success and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
                    insp.pdf_path = pdf_path
                    downloaded += 1

                    # Extract data from fresh PDF
                    data = extractor.extract_all(pdf_path)
                    if data.get("permit_id"):
                        insp.permit_id = data["permit_id"]
                    if data.get("program_identifier"):
                        insp.program_identifier = data["program_identifier"]
                    re_extracted += 1
                else:
                    failed += 1
                    insp.pdf_download_attempts = (insp.pdf_download_attempts or 0) + 1
                    if insp.pdf_download_attempts >= 3:
                        insp.pdf_permanently_missing = True
                        logger.warning(f"  Marked permanently missing: {insp.inspection_id}")

                # Commit periodically
                if (i + 1) % 10 == 0:
                    await db.flush()
                    logger.info(f"  [{i+1}/{len(inspections)}] downloaded={downloaded} failed={failed} exists={already_exists}")

                await asyncio.sleep(PAUSE_BETWEEN_DOWNLOADS)

            await db.flush()

    finally:
        await scraper.close()

    logger.info(f"\nDone. Downloaded: {downloaded} | Failed: {failed} | Already on disk: {already_exists} | Re-extracted: {re_extracted}")


if __name__ == "__main__":
    asyncio.run(main())
