#!/usr/bin/env python3
"""EMD slow backfill — gentle background scraper that works backwards from today to Jan 2024.

Designed to run continuously without triggering rate limits:
- Scrapes one day at a time
- 10-second pause between requests
- 30-second pause between days
- 2-minute pause between weeks
- Logs progress to a status file for monitoring
- Tracks what was found vs downloaded per day
- Can be stopped and resumed (skips already-scraped dates)

Usage:
    # Start (runs until Jan 2024 or stopped)
    nohup python scripts/emd_slow_backfill.py > /tmp/emd_slow_backfill.log 2>&1 &

    # Monitor progress
    cat /tmp/emd_backfill_status.json
    tail -f /tmp/emd_slow_backfill.log

    # Check what's been done
    python scripts/emd_slow_backfill.py --status
"""

import asyncio
import json
import sys
import os
import logging
from datetime import date, timedelta, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

STATUS_FILE = "/tmp/emd_backfill_status.json"
TARGET_START = date(2024, 1, 1)
PAUSE_BETWEEN_REQUESTS = 10  # seconds
PAUSE_BETWEEN_DAYS = 30  # seconds
PAUSE_BETWEEN_WEEKS = 120  # seconds (2 min)
PAUSE_ON_ERROR = 300  # seconds (5 min)


def load_status() -> dict:
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "started_at": None,
            "last_update": None,
            "current_date": None,
            "target_start": str(TARGET_START),
            "days_completed": 0,
            "total_found": 0,
            "total_new": 0,
            "total_pdfs": 0,
            "total_pdf_failed": 0,
            "total_skipped": 0,
            "errors": 0,
            "daily_log": {},  # "YYYY-MM-DD": {"found": N, "new": N, "pdfs": N, "failed": N}
            "state": "idle",
        }


def save_status(status: dict):
    status["last_update"] = datetime.now().isoformat()
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2, default=str)


def print_status():
    status = load_status()
    print(json.dumps(status, indent=2))
    print(f"\n--- Summary ---")
    print(f"State: {status['state']}")
    print(f"Current date: {status['current_date']}")
    print(f"Days completed: {status['days_completed']}")
    print(f"Found: {status['total_found']} | New: {status['total_new']} | PDFs: {status['total_pdfs']} | Failed: {status['total_pdf_failed']}")
    print(f"Errors: {status['errors']}")

    # Verify completeness
    daily = status.get("daily_log", {})
    mismatches = []
    for day, data in daily.items():
        found = data.get("found", 0)
        pdfs = data.get("pdfs", 0)
        failed = data.get("failed", 0)
        skipped = data.get("skipped", 0)
        accounted = pdfs + failed + skipped
        if found > 0 and accounted < found:
            mismatches.append(f"  {day}: found={found}, pdfs={pdfs}, failed={failed}, skipped={skipped}, gap={found - accounted}")
    if mismatches:
        print(f"\n--- Days with gaps (found > downloaded+skipped) ---")
        for m in mismatches[-20:]:
            print(m)
    else:
        print(f"\nAll days fully accounted for.")


async def run_backfill():
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from src.services.emd.service import EMDService
    from sqlalchemy import select
    from src.models.emd_inspection import EMDInspection

    status = load_status()
    status["started_at"] = status["started_at"] or datetime.now().isoformat()
    status["state"] = "running"

    # Resume from where we left off, or start from today
    if status["current_date"]:
        current = date.fromisoformat(status["current_date"]) - timedelta(days=1)
    else:
        current = date.today()

    scraper = EMDScraper(rate_limit_seconds=PAUSE_BETWEEN_REQUESTS)
    consecutive_errors = 0

    try:
        while current >= TARGET_START:
            date_str = current.strftime("%Y-%m-%d")
            status["current_date"] = date_str

            # Skip if already done AND fully accounted for
            existing_day = status.get("daily_log", {}).get(date_str)
            if existing_day:
                found = existing_day.get("found", 0)
                accounted = existing_day.get("pdfs", 0) + existing_day.get("skipped", 0)
                if found == 0 or accounted >= found:
                    current -= timedelta(days=1)
                    continue
                # Has gaps — retry this day
                logger.info(f"Retrying {date_str} (found={found}, accounted={accounted}, gap={found - accounted})")

            logger.info(f"Scraping {date_str}...")

            day_found = 0
            day_new = 0
            day_pdfs = 0
            day_failed = 0
            day_skipped = 0

            try:
                facilities = await scraper.scrape_date_range(date_str, date_str, max_load_more=20)
                day_found = len(facilities)
                logger.info(f"  {date_str}: found {day_found} facilities")

                if day_found > 0:
                    async with get_db_context() as db:
                        svc = EMDService(db)

                        for facility_data in facilities:
                            try:
                                inspection_id = facility_data.get("inspection_id")
                                if not inspection_id:
                                    day_skipped += 1
                                    continue

                                # Check if already in DB
                                existing = await db.execute(
                                    select(EMDInspection).where(EMDInspection.inspection_id == inspection_id)
                                )
                                if existing.scalar_one_or_none():
                                    day_skipped += 1
                                    continue

                                # Download PDF
                                pdf_path = None
                                pdf_url = facility_data.get("pdf_url")
                                if pdf_url:
                                    year_dir = os.path.join(
                                        os.path.dirname(__file__), "..", "uploads", "emd",
                                        current.strftime("%Y")
                                    )
                                    os.makedirs(year_dir, exist_ok=True)
                                    pdf_path = os.path.join(year_dir, f"{inspection_id}.pdf")

                                    if not os.path.exists(pdf_path):
                                        success = await scraper.download_pdf(pdf_url, pdf_path)
                                        if success:
                                            day_pdfs += 1
                                        else:
                                            day_failed += 1
                                            pdf_path = None
                                    else:
                                        day_pdfs += 1  # Already on disk

                                # Save to DB
                                result = await svc.process_facility(facility_data, pdf_path=pdf_path)
                                if result in ("new_facility", "new_inspection"):
                                    day_new += 1

                            except Exception as e:
                                logger.warning(f"  Error: {facility_data.get('name')}: {e}")
                                day_failed += 1
                                try:
                                    await db.rollback()
                                except Exception:
                                    pass
                                continue

                consecutive_errors = 0

            except Exception as e:
                logger.error(f"  Scrape error for {date_str}: {e}")
                status["errors"] = status.get("errors", 0) + 1
                consecutive_errors += 1

                if consecutive_errors >= 3:
                    logger.warning(f"  3 consecutive errors, pausing {PAUSE_ON_ERROR}s and restarting browser")
                    try:
                        await scraper.close()
                    except Exception:
                        pass
                    await asyncio.sleep(PAUSE_ON_ERROR)
                    consecutive_errors = 0

            # Update status
            status["total_found"] = status.get("total_found", 0) + day_found
            status["total_new"] = status.get("total_new", 0) + day_new
            status["total_pdfs"] = status.get("total_pdfs", 0) + day_pdfs
            status["total_pdf_failed"] = status.get("total_pdf_failed", 0) + day_failed
            status["total_skipped"] = status.get("total_skipped", 0) + day_skipped
            status["days_completed"] = status.get("days_completed", 0) + 1

            if "daily_log" not in status:
                status["daily_log"] = {}
            prev = status["daily_log"].get(date_str, {})
            status["daily_log"][date_str] = {
                "found": max(day_found, prev.get("found", 0)),
                "new": prev.get("new", 0) + day_new,
                "pdfs": prev.get("pdfs", 0) + day_pdfs,
                "failed": day_failed,  # Reset failed count on retry
                "skipped": prev.get("skipped", 0) + day_skipped,
            }

            save_status(status)

            if day_found > 0:
                logger.info(f"  {date_str}: new={day_new}, pdfs={day_pdfs}, failed={day_failed}, skipped={day_skipped}")

            # Pace ourselves
            current -= timedelta(days=1)
            is_week_boundary = current.weekday() == 6  # Sunday
            if is_week_boundary:
                logger.info(f"  Week boundary, pausing {PAUSE_BETWEEN_WEEKS}s...")
                await asyncio.sleep(PAUSE_BETWEEN_WEEKS)
            else:
                await asyncio.sleep(PAUSE_BETWEEN_DAYS)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        status["state"] = "stopped"
        save_status(status)
        try:
            await scraper.close()
        except Exception:
            pass
        logger.info(f"Backfill stopped at {status['current_date']}")
        logger.info(f"Total: found={status['total_found']}, new={status['total_new']}, pdfs={status['total_pdfs']}")


def main():
    if "--status" in sys.argv:
        print_status()
        return

    asyncio.run(run_backfill())


if __name__ == "__main__":
    main()
