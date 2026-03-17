#!/usr/bin/env python3
"""EMD inspection backfill — scrape historical inspections working backwards.

Usage:
    # Scrape last 30 days
    python scripts/emd_backfill.py

    # Scrape specific month
    python scripts/emd_backfill.py --start 2025-06-01 --end 2025-06-30

    # Daily mode (just yesterday + today)
    python scripts/emd_backfill.py --daily

    # Full backfill from a date (slow, rate limited)
    python scripts/emd_backfill.py --start 2024-01-01 --end 2025-12-31
"""

import asyncio
import argparse
import sys
import os
import logging
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run_backfill(start_date: date, end_date: date, rate_limit: int = 5):
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from src.services.emd.service import EMDService

    scraper = EMDScraper(rate_limit_seconds=rate_limit)
    total_scraped = 0
    total_new = 0
    total_pdfs = 0

    try:
        # Work through date range in weekly chunks
        current = start_date
        while current <= end_date:
            chunk_end = min(current + timedelta(days=6), end_date)
            start_str = current.strftime("%Y-%m-%d")
            end_str = chunk_end.strftime("%Y-%m-%d")

            logger.info(f"Scraping {start_str} to {end_str}...")

            try:
                facilities = await scraper.scrape_date_range(start_str, end_str, max_load_more=20)
                total_scraped += len(facilities)
                logger.info(f"  Found {len(facilities)} facilities")

                async with get_db_context() as db:
                    svc = EMDService(db)

                    for facility_data in facilities:
                        try:
                            inspection_id = facility_data.get("inspection_id")
                            if not inspection_id:
                                continue

                            # Download PDF first (so process_facility can extract it)
                            pdf_url = facility_data.get("pdf_url")
                            pdf_path = None
                            if pdf_url:
                                pdf_dir = os.path.join(
                                    os.path.dirname(__file__), "..", "uploads", "emd",
                                    current.strftime("%Y")
                                )
                                os.makedirs(pdf_dir, exist_ok=True)
                                pdf_path = os.path.join(pdf_dir, f"{inspection_id}.pdf")

                                if not os.path.exists(pdf_path):
                                    success = await scraper.download_pdf(pdf_url, pdf_path)
                                    if success:
                                        total_pdfs += 1
                                    else:
                                        pdf_path = None

                            # Process facility (creates facility + inspection + extracts PDF)
                            result = await svc.process_facility(facility_data, pdf_path=pdf_path)
                            if result in ("new_facility", "new_inspection"):
                                total_new += 1
                                logger.info(f"    {result}: {facility_data.get('name')}")

                        except Exception as e:
                            logger.warning(f"  Error processing {facility_data.get('name')}: {e}")
                            continue

            except Exception as e:
                logger.error(f"  Scrape failed for {start_str} to {end_str}: {e}")

            current = chunk_end + timedelta(days=1)
            logger.info(f"  Running total: {total_scraped} scraped, {total_new} new, {total_pdfs} PDFs")

    finally:
        await scraper.close()

    logger.info(f"\n=== BACKFILL COMPLETE ===")
    logger.info(f"Scraped: {total_scraped} facilities")
    logger.info(f"New: {total_new} inspections")
    logger.info(f"PDFs: {total_pdfs} downloaded")


def main():
    parser = argparse.ArgumentParser(description="EMD inspection backfill")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    parser.add_argument("--daily", action="store_true", help="Daily mode (yesterday + today)")
    parser.add_argument("--rate-limit", type=int, default=5, help="Seconds between requests")
    args = parser.parse_args()

    if args.daily:
        today = date.today()
        start = today - timedelta(days=1)
        end = today
    elif args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        # Default: last 30 days
        today = date.today()
        start = today - timedelta(days=30)
        end = today

    logger.info(f"EMD Backfill: {start} to {end} (rate limit: {args.rate_limit}s)")
    asyncio.run(run_backfill(start, end, args.rate_limit))


if __name__ == "__main__":
    main()
