#!/usr/bin/env python3
"""Backfill inspection data from the EMD portal.

Compares what we have in the DB vs what the portal has for each date,
imports missing inspections, and runs QC checks on random dates.

Designed to be gentle on the EMD site: reuses a single browser session,
pauses between requests, backs off on failures, and skips dates where
DB already matches the portal count.

Usage:
    python scripts/backfill_inspections.py                    # full 2024+2025 backfill
    python scripts/backfill_inspections.py --qc-only          # just run QC checks
    python scripts/backfill_inspections.py --year 2025        # single year
    python scripts/backfill_inspections.py --month 2025-07    # single month
"""

import asyncio
import argparse
import json
import logging
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "inspection")
RATE_LIMIT_SECONDS = 8
PAUSE_BETWEEN_DAYS = 15
PAUSE_BETWEEN_MONTHS = 45
FAILURE_BACKOFF = 60  # seconds to wait after a scrape failure
MAX_CONSECUTIVE_FAILURES = 3  # abort after this many in a row


def date_range(start: date, end: date):
    """Yield each weekday from start to end inclusive."""
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


async def get_db_counts_by_date(start: date, end: date) -> dict[str, int]:
    """Get inspection counts per date from our DB."""
    from src.core.database import get_db_context
    from sqlalchemy import text

    async with get_db_context() as db:
        r = await db.execute(text("""
            SELECT inspection_date, COUNT(*) as cnt
            FROM inspections
            WHERE inspection_date >= :start AND inspection_date <= :end
            GROUP BY inspection_date
        """), {"start": start, "end": end})
        return {str(row[0]): row[1] for row in r.fetchall()}


async def get_db_ids_for_date(d: date) -> set[str]:
    """Get all inspection_ids for a given date."""
    from src.core.database import get_db_context
    from sqlalchemy import text

    async with get_db_context() as db:
        r = await db.execute(text(
            "SELECT inspection_id FROM inspections WHERE inspection_date = :d"
        ), {"d": d})
        return {row[0] for row in r.fetchall()}


async def import_facilities(facilities: list[dict], target_date: date, scraper) -> dict:
    """Import missing facilities into the DB. Returns stats dict."""
    from src.core.database import get_db_context
    from src.services.inspection.service import InspectionService
    from src.services.inspection.pdf_extractor import EMDPDFExtractor
    from src.models.inspection import Inspection
    from src.models.organization import Organization
    from sqlalchemy import select

    extractor = EMDPDFExtractor()
    stats = {"new": 0, "pdfs": 0, "skipped": 0, "errors": []}

    async with get_db_context() as db:
        svc = InspectionService(db)
        existing_ids = await get_db_ids_for_date(target_date)

        for fdata in facilities:
            inspection_id = fdata.get("inspection_id")
            if not inspection_id:
                continue

            if inspection_id in existing_ids:
                stats["skipped"] += 1
                continue

            try:
                # Download PDF
                pdf_path = None
                pdf_url = fdata.get("pdf_url")
                if pdf_url:
                    year_dir = os.path.join(UPLOADS_DIR, target_date.strftime("%Y"))
                    os.makedirs(year_dir, exist_ok=True)
                    pdf_path = os.path.join(year_dir, f"{inspection_id}.pdf")

                    if not os.path.exists(pdf_path):
                        success = await scraper.download_pdf(pdf_url, pdf_path)
                        if success and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
                            stats["pdfs"] += 1
                        else:
                            pdf_path = None
                    else:
                        stats["pdfs"] += 1  # already on disk

                # Import
                save_result = await svc.process_facility(fdata, pdf_path=pdf_path)
                if save_result in ("new_facility", "new_inspection"):
                    stats["new"] += 1

                    # Extract PDF metadata
                    if pdf_path and os.path.exists(pdf_path):
                        insp_record = await db.execute(
                            select(Inspection).where(Inspection.inspection_id == inspection_id)
                        )
                        insp = insp_record.scalar_one_or_none()
                        if insp:
                            data = extractor.extract_all(pdf_path)
                            if data.get("permit_id"):
                                insp.permit_id = data["permit_id"]
                            if data.get("program_identifier"):
                                insp.program_identifier = data["program_identifier"]

            except Exception as e:
                stats["errors"].append(f"{fdata.get('name', '?')}: {e}")
                logger.warning(f"    Error: {fdata.get('name', '?')}: {e}")

            await asyncio.sleep(RATE_LIMIT_SECONDS)

        # Auto-match new facilities
        if stats["new"] > 0:
            try:
                org_result = await db.execute(select(Organization).limit(1))
                org = org_result.scalar_one_or_none()
                if org:
                    match_result = await svc.auto_match_facilities(org.id)
                    if match_result.get("matched", 0) > 0:
                        logger.info(f"    Auto-matched {match_result['matched']} facilities")
            except Exception as e:
                logger.warning(f"    Auto-match error: {e}")

    return stats


async def backfill_bulk(start: date, end: date):
    """Bulk backfill: query entire date range at once. Best for off-season
    months where few/no inspections exist — one scrape covers months."""
    from src.services.inspection.scraper import EMDScraper

    end = min(end, date.today())
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    logger.info(f"Bulk scrape: {start_str} to {end_str}")

    totals = {"days_checked": 1, "days_with_gaps": 0, "new": 0, "pdfs": 0, "errors": 0, "skipped_match": 0}

    # Get all existing inspection IDs for this range
    existing_ids = set()
    db_counts = await get_db_counts_by_date(start, end)
    total_db = sum(db_counts.values())

    for d in date_range(start, end):
        ids = await get_db_ids_for_date(d)
        existing_ids.update(ids)

    logger.info(f"  DB has {total_db} inspections across {len(db_counts)} dates")

    scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)
    try:
        facilities = await scraper.scrape_date_range(start_str, end_str, max_load_more=30)
        portal_count = len(facilities)
        logger.info(f"  Portal returned {portal_count} inspections")

        # Filter to only new ones
        new_facilities = [f for f in facilities if f.get("inspection_id") and f["inspection_id"] not in existing_ids]

        if not new_facilities:
            logger.info(f"  All {portal_count} already in DB — nothing to import")
            totals["skipped_match"] = 1
            return totals

        logger.info(f"  {len(new_facilities)} new inspections to import")
        totals["days_with_gaps"] = 1

        # Group by date for import (need to pass the right date for PDF paths)
        from collections import defaultdict
        by_date = defaultdict(list)
        for f in new_facilities:
            d_str = f.get("inspection_date", start_str)
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                d = start
            by_date[d].append(f)

        for d, facs in sorted(by_date.items()):
            logger.info(f"  {d}: importing {len(facs)} new")
            stats = await import_facilities(facs, d, scraper)
            totals["new"] += stats["new"]
            totals["pdfs"] += stats["pdfs"]
            totals["errors"] += len(stats["errors"])

    except Exception as e:
        logger.error(f"  Bulk scrape failed: {e}")
        totals["errors"] += 1
    finally:
        await scraper.close()

    return totals


async def backfill_daily(start: date, end: date):
    """Daily backfill: scrape one day at a time. Best for peak season
    where each day can have 40-60+ inspections."""
    from src.services.inspection.scraper import EMDScraper

    end = min(end, date.today())
    logger.info(f"Daily scrape: {start} to {end}")

    db_counts = await get_db_counts_by_date(start, end)
    logger.info(f"DB has inspections on {len(db_counts)} dates in this range")

    totals = {"days_checked": 0, "days_with_gaps": 0, "new": 0, "pdfs": 0, "errors": 0, "skipped_match": 0}
    current_month = None
    consecutive_failures = 0

    scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)

    try:
        for d in date_range(start, end):
            month = d.strftime("%Y-%m")
            if month != current_month:
                if current_month is not None:
                    logger.info(f"  Pausing at month boundary ({PAUSE_BETWEEN_MONTHS}s)...")
                    await asyncio.sleep(PAUSE_BETWEEN_MONTHS)
                current_month = month
                logger.info(f"\n=== {month} ===")

            date_str = d.strftime("%Y-%m-%d")
            db_count = db_counts.get(date_str, 0)
            totals["days_checked"] += 1

            try:
                facilities = await scraper.scrape_date_range(date_str, date_str, max_load_more=20)
                portal_count = len(facilities)
                consecutive_failures = 0

                if portal_count == 0 and db_count == 0:
                    continue

                if portal_count == db_count:
                    totals["skipped_match"] += 1
                    logger.info(f"  {date_str}: ={db_count} (matches)")
                    await asyncio.sleep(PAUSE_BETWEEN_DAYS)
                    continue

                if portal_count < db_count:
                    logger.warning(f"  {date_str}: DB={db_count} > portal={portal_count} (possible Load More issue, skipping)")
                    await asyncio.sleep(PAUSE_BETWEEN_DAYS)
                    continue

                gap = portal_count - db_count
                logger.info(f"  {date_str}: DB={db_count}, portal={portal_count}, gap={gap} — importing")

                stats = await import_facilities(facilities, d, scraper)
                totals["days_with_gaps"] += 1
                totals["new"] += stats["new"]
                totals["pdfs"] += stats["pdfs"]
                totals["errors"] += len(stats["errors"])

                if stats["new"] > 0:
                    logger.info(f"    Imported {stats['new']} new, {stats['pdfs']} PDFs")

            except Exception as e:
                consecutive_failures += 1
                logger.error(f"  {date_str}: scrape failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {e}")
                totals["errors"] += 1

                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(f"  Aborting — {MAX_CONSECUTIVE_FAILURES} consecutive failures")
                    break

                logger.info(f"  Backing off {FAILURE_BACKOFF}s...")
                await asyncio.sleep(FAILURE_BACKOFF)
                try:
                    await scraper.close()
                except Exception:
                    pass
                scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)
                continue

            await asyncio.sleep(PAUSE_BETWEEN_DAYS)

    finally:
        await scraper.close()

    return totals


async def backfill(start: date, end: date, mode: str = "daily"):
    """Route to bulk or daily backfill."""
    if mode == "bulk":
        return await backfill_bulk(start, end)
    else:
        return await backfill_daily(start, end)


async def run_qc_checks(start: date, end: date, num_checks: int = 10) -> list[dict]:
    """Pick random dates and verify DB matches portal by inspection ID."""
    from src.services.inspection.scraper import EMDScraper

    weekdays = list(date_range(start, min(end, date.today())))
    if not weekdays:
        logger.warning("No weekdays in range for QC")
        return []

    sample_dates = random.sample(weekdays, min(num_checks, len(weekdays)))
    sample_dates.sort()

    results = []
    scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)

    try:
        for d in sample_dates:
            date_str = d.strftime("%Y-%m-%d")

            try:
                facilities = await scraper.scrape_date_range(date_str, date_str, max_load_more=20)
                portal_ids = {f["inspection_id"] for f in facilities if f.get("inspection_id")}
                db_ids = await get_db_ids_for_date(d)

                missing = portal_ids - db_ids
                extra = db_ids - portal_ids

                status = "OK" if not missing and not extra else "MISMATCH"
                result = {
                    "date": date_str,
                    "portal": len(portal_ids),
                    "db": len(db_ids),
                    "missing": len(missing),
                    "extra": len(extra),
                    "status": status,
                }
                results.append(result)

                icon = "✓" if status == "OK" else "✗"
                logger.info(f"  QC {date_str}: portal={len(portal_ids)} db={len(db_ids)} "
                            f"missing={len(missing)} extra={len(extra)} {icon}")

            except Exception as e:
                results.append({"date": date_str, "status": "ERROR", "error": str(e)})
                logger.error(f"  QC {date_str}: {e}")
                # Restart browser
                try:
                    await scraper.close()
                except Exception:
                    pass
                scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)

            await asyncio.sleep(PAUSE_BETWEEN_DAYS)

    finally:
        await scraper.close()

    return results


def merge_totals(all_totals: list[dict]) -> dict:
    """Merge multiple backfill result dicts."""
    merged = {"days_checked": 0, "days_with_gaps": 0, "new": 0, "pdfs": 0, "errors": 0, "skipped_match": 0}
    for t in all_totals:
        for k in merged:
            merged[k] += t.get(k, 0)
    return merged


async def main():
    parser = argparse.ArgumentParser(description="Backfill EMD inspection data")
    parser.add_argument("--qc-only", action="store_true", help="Only run QC checks")
    parser.add_argument("--year", type=int, help="Single year (e.g. 2025)")
    parser.add_argument("--month", type=str, help="Single month (e.g. 2025-07)")
    parser.add_argument("--range", type=str, help="Date range YYYY-MM-DD:YYYY-MM-DD")
    parser.add_argument("--season", type=int, help="Run full season strategy for a year (bulk off-season, daily peak)")
    parser.add_argument("--qc-count", type=int, default=10, help="Number of QC sample dates")
    args = parser.parse_args()

    ranges = []

    if args.season:
        y = args.season
        # Off-season: bulk scrape entire range in one query (few/no inspections)
        # Peak: daily scrape May–Aug (high volume, avoid Load More issues)
        ranges = [
            (date(y, 1, 1), date(y, 4, 30), "off-season Jan-Apr", "bulk"),
            (date(y, 5, 1), date(y, 8, 31), "peak May-Aug", "daily"),
            (date(y, 9, 1), date(y, 12, 31), "off-season Sep-Dec", "bulk"),
        ]
    elif args.range:
        s, e = args.range.split(":")
        start = date.fromisoformat(s)
        end = date.fromisoformat(e)
        ranges = [(start, end, f"{s} to {e}", "daily")]
    elif args.month:
        y, m = map(int, args.month.split("-"))
        start = date(y, m, 1)
        end = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
        ranges = [(start, end, f"{args.month}", "daily")]
    elif args.year:
        ranges = [(date(args.year, 1, 1), date(args.year, 12, 31), str(args.year), "daily")]
    elif not args.qc_only:
        # Default: run season strategy for both 2024 and 2025
        for y in [2024, 2025]:
            ranges.extend([
                (date(y, 1, 1), date(y, 4, 30), f"{y} off-season Jan-Apr", "bulk"),
                (date(y, 5, 1), date(y, 8, 31), f"{y} peak May-Aug", "daily"),
                (date(y, 9, 1), date(y, 12, 31), f"{y} off-season Sep-Dec", "bulk"),
            ])

    all_totals = []
    qc_start = None
    qc_end = None

    if not args.qc_only and ranges:
        logger.info("=" * 60)
        logger.info("PHASE 1: BACKFILL")
        logger.info("=" * 60)

        for start, end, label, mode in ranges:
            logger.info(f"\n{'='*40}")
            logger.info(f"  {label} ({mode})")
            logger.info(f"{'='*40}")
            totals = await backfill(start, end, mode=mode)
            all_totals.append(totals)

            if qc_start is None or start < qc_start:
                qc_start = start
            if qc_end is None or end > qc_end:
                qc_end = end

            # Pause between phases
            logger.info(f"  Phase pause (60s)...")
            await asyncio.sleep(60)

        merged = merge_totals(all_totals)
        logger.info("")
        logger.info("Backfill complete:")
        logger.info(f"  Days checked:     {merged['days_checked']}")
        logger.info(f"  Days matched:     {merged['skipped_match']}")
        logger.info(f"  Days with gaps:   {merged['days_with_gaps']}")
        logger.info(f"  New imported:     {merged['new']}")
        logger.info(f"  PDFs fetched:     {merged['pdfs']}")
        logger.info(f"  Errors:           {merged['errors']}")

    # Determine QC range
    if args.qc_only:
        if args.range:
            s, e = args.range.split(":")
            qc_start, qc_end = date.fromisoformat(s), date.fromisoformat(e)
        elif args.month:
            y, m = map(int, args.month.split("-"))
            qc_start = date(y, m, 1)
            qc_end = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
        elif args.year:
            qc_start, qc_end = date(args.year, 1, 1), date(args.year, 12, 31)
        elif args.season:
            qc_start, qc_end = date(args.season, 1, 1), date(args.season, 12, 31)
        else:
            qc_start, qc_end = date(2024, 1, 1), date(2025, 12, 31)

    if qc_start and qc_end:
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"PHASE 2: QC CHECKS ({args.qc_count} random dates)")
        logger.info("=" * 60)
        qc_results = await run_qc_checks(qc_start, qc_end, num_checks=args.qc_count)

        ok = sum(1 for r in qc_results if r["status"] == "OK")
        fail = sum(1 for r in qc_results if r["status"] == "MISMATCH")
        err = sum(1 for r in qc_results if r["status"] == "ERROR")
        logger.info(f"\nQC Summary: {ok} OK, {fail} mismatch, {err} errors out of {len(qc_results)} checks")

        if fail > 0:
            logger.warning("MISMATCHES FOUND — re-run for affected dates")

    # Save report
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "qc_results": qc_results if qc_start else [],
    }
    if all_totals:
        report["backfill"] = merge_totals(all_totals)
    report_path = "/tmp/backfill_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
