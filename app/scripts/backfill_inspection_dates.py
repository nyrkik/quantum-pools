"""Re-extract inspection_date from each inspection's PDF and update the column.

Background: a pre-2026-04-06 scraper bug stamped inspection_date from
search_date instead of from the PDF/portal. This contaminates ~2169 records
across the 2026-03-17, 2026-04-06, and 2026-04-07 ingestion runs. Commit
876600e fixed the scraper but the bad data was never backfilled.

Strategy: walk every inspection with a PDF on disk, re-extract the
canonical date, update the column when it differs.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_inspection_dates.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/backfill_inspection_dates.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.services.inspection.pdf_extractor import EMDPDFExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def main(dry_run: bool):
    extractor = EMDPDFExtractor()
    stats = {
        "total": 0,
        "no_pdf": 0,
        "pdf_missing_on_disk": 0,
        "extract_failed": 0,
        "no_date_in_pdf": 0,
        "already_correct": 0,
        "updated": 0,
    }

    async with get_db_context() as db:
        result = await db.execute(select(Inspection))
        all_insp = result.scalars().all()
        stats["total"] = len(all_insp)
        logger.info(f"Walking {len(all_insp)} inspections")

        for insp in all_insp:
            if not insp.pdf_path:
                stats["no_pdf"] += 1
                continue

            try:
                p = Path(insp.pdf_path).resolve()
            except Exception:
                stats["pdf_missing_on_disk"] += 1
                continue

            if not p.exists():
                stats["pdf_missing_on_disk"] += 1
                continue

            try:
                pdf_data = extractor.extract_all(str(p))
            except Exception as e:
                logger.warning(f"  extract failed for {insp.inspection_id}: {e}")
                stats["extract_failed"] += 1
                continue

            actual_str = pdf_data.get("inspection_date")
            if not actual_str:
                stats["no_date_in_pdf"] += 1
                continue

            try:
                actual_date = datetime.strptime(actual_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                stats["no_date_in_pdf"] += 1
                continue

            if insp.inspection_date == actual_date:
                stats["already_correct"] += 1
                continue

            stats["updated"] += 1
            if not dry_run:
                insp.inspection_date = actual_date

            if stats["updated"] % 200 == 0:
                logger.info(
                    f"  progress: updated={stats['updated']} correct={stats['already_correct']} "
                    f"of {stats['total']}"
                )

        if dry_run:
            await db.rollback()
            logger.info("\nDRY RUN — rolled back")
        else:
            await db.commit()
            logger.info("\nCommitted")

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
