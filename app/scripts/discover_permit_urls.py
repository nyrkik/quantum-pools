"""Discovery: walk every inspection in the DB and populate `permit_url` by
asking the scraper for the inspection page's back-link.

Why this approach: the date-search listing collapses multi-BoW siblings, so
permit URLs for "hidden" inspections are NEVER exposed by the listing. The
inspection page itself contains a direct link to its parent permit page.

Rate-limit discipline: this script does NOT manage its own pages, contexts,
concurrency, or rate limits. It just calls `scraper.get_inspection_permit_url()`
in a loop. The scraper class enforces:
  - Sequential portal access via an asyncio.Lock (no parallel requests)
  - `rate_limit_seconds` minimum interval between any two portal requests
  - Process-wide circuit breaker on HTTP 403/429 (raises PortalBlocked)

If the scraper raises PortalBlocked, this script aborts immediately. Re-run
later (next day if necessary) — it picks up where it left off because it
only processes records where `permit_url IS NULL`.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/discover_permit_urls.py --limit 5
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/discover_permit_urls.py
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.services.inspection.scraper import InspectionScraper, PortalBlocked

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def main(dry_run: bool, all_records: bool, limit: int | None, rate_limit: int):
    async with get_db_context() as db:
        query = select(Inspection.id, Inspection.inspection_id).where(
            Inspection.inspection_id.isnot(None)
        )
        if not all_records:
            query = query.where(Inspection.permit_url.is_(None))
        if limit:
            query = query.limit(limit)
        rows = (await db.execute(query)).all()

    eta_min = (len(rows) * rate_limit) // 60
    logger.info(
        f"Discovery: {len(rows)} inspections to process at {rate_limit}s/req "
        f"(~{eta_min} min, {eta_min//60}h{eta_min%60}m)"
    )

    stats = {"total": len(rows), "processed": 0, "found": 0, "not_found": 0}

    scraper = InspectionScraper(rate_limit_seconds=rate_limit)
    try:
        for row_id, inspection_id in rows:
            try:
                permit_url = await scraper.get_inspection_permit_url(inspection_id)
            except PortalBlocked as e:
                logger.error(f"ABORTING: {e}")
                break

            if permit_url:
                stats["found"] += 1
                if not dry_run:
                    async with get_db_context() as db:
                        await db.execute(
                            update(Inspection).where(Inspection.id == row_id).values(permit_url=permit_url)
                        )
                        await db.commit()
            else:
                stats["not_found"] += 1

            stats["processed"] += 1
            if stats["processed"] % 25 == 0:
                logger.info(
                    f"  progress: {stats['processed']}/{stats['total']} "
                    f"(found={stats['found']} not_found={stats['not_found']})"
                )
    finally:
        await scraper.close()

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    if dry_run:
        logger.info("(dry run — no commits)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--all", action="store_true", help="Re-process all (default: only NULL permit_url)")
    p.add_argument("--rate-limit", type=int, default=8, help="Seconds between requests (default 8)")
    p.add_argument("--limit", type=int, default=None, help="Process at most N (for cautious testing)")
    args = p.parse_args()
    asyncio.run(main(
        dry_run=args.dry_run,
        all_records=args.all,
        limit=args.limit,
        rate_limit=args.rate_limit,
    ))
