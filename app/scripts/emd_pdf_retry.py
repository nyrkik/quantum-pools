#!/usr/bin/env python3
"""Retry downloading missing EMD inspection PDFs.

Finds inspections where:
- pdf_path is NULL (never downloaded)
- pdf_path points to /mnt (NAS path, inaccessible)
- pdf_path set but file doesn't exist on disk

Downloads via Playwright scraper, updates DB path.
Marks as permanently_missing after 3 failed attempts.

Usage:
    python scripts/emd_pdf_retry.py           # Run retry
    python scripts/emd_pdf_retry.py --status   # Show status
"""

import asyncio
import json
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STATUS_FILE = "/tmp/emd_pdf_retry_status.json"
PAUSE_BETWEEN_DOWNLOADS = 10


def load_status() -> dict:
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"state": "idle", "total": 0, "downloaded": 0, "failed": 0, "permanently_missing": 0, "missing_ids": []}


def save_status(status: dict):
    status["last_update"] = datetime.now().isoformat()
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2, default=str)


async def run_retry():
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from sqlalchemy import select, or_
    from src.models.emd_inspection import EMDInspection

    status = load_status()
    status["state"] = "running"
    status["started_at"] = datetime.now().isoformat()
    save_status(status)

    async with get_db_context() as db:
        # Find inspections needing PDFs
        result = await db.execute(
            select(EMDInspection).where(
                EMDInspection.pdf_permanently_missing == False,
                EMDInspection.inspection_id.isnot(None),
                or_(
                    EMDInspection.pdf_path.is_(None),
                    EMDInspection.pdf_path.like("/mnt%"),
                ),
            ).order_by(EMDInspection.inspection_date.desc())
        )
        inspections = result.scalars().all()
        status["total"] = len(inspections)
        save_status(status)
        logger.info(f"Found {len(inspections)} inspections needing PDFs")

        if not inspections:
            status["state"] = "complete"
            save_status(status)
            return

        scraper = EMDScraper(rate_limit_seconds=PAUSE_BETWEEN_DOWNLOADS)

        try:
            for i, insp in enumerate(inspections):
                # Build expected PDF path
                year = str(insp.inspection_date.year) if insp.inspection_date else "unknown"
                year_dir = os.path.join(
                    os.path.dirname(__file__), "..", "uploads", "emd", year
                )
                os.makedirs(year_dir, exist_ok=True)
                pdf_path = os.path.join(year_dir, f"{insp.inspection_id}.pdf")

                # Skip if already on disk
                if os.path.exists(pdf_path):
                    insp.pdf_path = pdf_path
                    status["downloaded"] += 1
                    if (i + 1) % 50 == 0:
                        await db.commit()
                        save_status(status)
                    continue

                # Try to download via inspection page
                success = await scraper.download_pdf_by_inspection_id(insp.inspection_id, pdf_path)

                if success and os.path.exists(pdf_path):
                    insp.pdf_path = pdf_path
                    insp.pdf_download_attempts = (insp.pdf_download_attempts or 0) + 1
                    status["downloaded"] += 1
                    logger.info(f"  [{i+1}/{len(inspections)}] Downloaded {insp.inspection_id}")
                else:
                    insp.pdf_download_attempts = (insp.pdf_download_attempts or 0) + 1
                    if insp.pdf_download_attempts >= 3:
                        insp.pdf_permanently_missing = True
                        status["permanently_missing"] += 1
                        status["missing_ids"].append(insp.inspection_id)
                        logger.warning(f"  [{i+1}/{len(inspections)}] Permanently missing: {insp.inspection_id}")
                    else:
                        status["failed"] += 1
                        logger.warning(f"  [{i+1}/{len(inspections)}] Failed (attempt {insp.pdf_download_attempts}): {insp.inspection_id}")

                if (i + 1) % 10 == 0:
                    await db.commit()
                    save_status(status)
                    logger.info(f"  Progress: {i+1}/{len(inspections)} | downloaded={status['downloaded']} failed={status['failed']} missing={status['permanently_missing']}")

                await asyncio.sleep(PAUSE_BETWEEN_DOWNLOADS)

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            await db.commit()
            status["state"] = "complete"
            save_status(status)
            try:
                await scraper.close()
            except Exception:
                pass
            logger.info(f"Done: downloaded={status['downloaded']} failed={status['failed']} missing={status['permanently_missing']}")


def main():
    if "--status" in sys.argv:
        status = load_status()
        print(json.dumps(status, indent=2))
        return
    asyncio.run(run_retry())


if __name__ == "__main__":
    main()
