"""Spot-check QC: pick N random dates and verify DB inspection_ids match
what the Sacramento County portal returns for that date.

Reports any drift per-date (missing-from-DB or extra-in-DB) and an overall
pass/fail. Uses the rate-limited scraper, so safe to run on demand without
tripping the WAF.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/qc_inspections.py
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/qc_inspections.py --count 20
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/qc_inspections.py --year 2024 --count 5
"""

import argparse
import asyncio
import logging
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.services.inspection.scraper import InspectionScraper, PortalBlocked

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Sacramento swim season: pool inspections concentrate May–Sept
SWIM_SEASON_MONTHS = (5, 9)


def smart_default_year() -> int:
    """Pick the right year to sample from for a meaningful QC.

    During swim season (May–Sept): use current year so we test the most
    recent heavy-load data the scraper has been ingesting.
    Outside swim season: use previous year because the current year has
    nothing meaningful to test against.
    """
    today = date.today()
    if SWIM_SEASON_MONTHS[0] <= today.month <= SWIM_SEASON_MONTHS[1]:
        return today.year
    return today.year - 1


def random_swim_season_dates(year: int, n: int) -> list[date]:
    """Pick N distinct random dates from the swim season of `year`."""
    start = date(year, SWIM_SEASON_MONTHS[0], 1)
    if SWIM_SEASON_MONTHS[1] == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, SWIM_SEASON_MONTHS[1] + 1, 1) - timedelta(days=1)
    end = min(end, date.today())
    if end < start:
        return []
    all_days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    # weekday only — inspections rarely happen on weekends
    weekdays = [d for d in all_days if d.weekday() < 5]
    if len(weekdays) <= n:
        return weekdays
    return sorted(random.sample(weekdays, n))


def recent_weekdays(n: int) -> list[date]:
    """Return the most recent N weekdays (not including today).

    NOTE: this is a naive walk-back. Used as a candidate pool — caller filters
    out days with no inspections (empty days don't validate anything).
    """
    out = []
    d = date.today() - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


async def find_recent_busy_dates(scraper, target_count: int, max_lookback_weekdays: int = 90) -> list[date]:
    """Walk backward from yesterday and collect dates that actually have
    inspection activity (DB rows OR portal results > 0).

    Empty days get skipped — they prove nothing in QC. In off-season this
    naturally reaches back into the previous swim season; in swim season it
    tests the last few real inspection days.
    """
    busy: list[date] = []
    d = date.today() - timedelta(days=1)
    checked = 0
    while len(busy) < target_count and checked < max_lookback_weekdays:
        if d.weekday() < 5:
            checked += 1
            d_str = d.strftime("%Y-%m-%d")

            # Cheap check first: does the DB have any inspections for this date?
            async with get_db_context() as db:
                row = (await db.execute(
                    select(Inspection.id).where(Inspection.inspection_date == d).limit(1)
                )).first()
                db_has = bool(row)

            if db_has:
                busy.append(d)
            else:
                # DB is empty for this date — verify the portal also says zero
                # before skipping. (If DB is empty but portal has results, that
                # IS a real drift we should flag.)
                try:
                    facs = await scraper.scrape_date_range(d_str, d_str, max_load_more=10)
                    if facs:
                        busy.append(d)
                    # Otherwise empty day — skip it, doesn't validate anything
                except PortalBlocked:
                    raise
                except Exception as e:
                    logger.warning(f"  pre-check {d_str}: {e}")
        d -= timedelta(days=1)
    return sorted(busy)


async def main(year: int, count: int, recent: bool, alert_on_mismatch: bool):
    scraper = InspectionScraper(rate_limit_seconds=8)

    if recent:
        # Walk backwards from yesterday, skipping empty days, until we find
        # `count` days that actually have inspection activity. In off-season
        # this naturally reaches back into the prior swim season — that's the
        # whole point. Empty days don't validate anything.
        try:
            sample_dates = await find_recent_busy_dates(scraper, count, max_lookback_weekdays=90)
        except PortalBlocked as e:
            logger.error(f"ABORTING during pre-scan: {e}")
            if alert_on_mismatch:
                from _notify import alert_failure
                alert_failure(
                    "inspection QC",
                    f"QC pre-scan blocked by portal WAF (403/429).\n{e}\n\nThe portal block typically clears within 24h. If this persists across multiple cron runs, investigate cumulative request volume.",
                    cooldown_seconds=6 * 3600,
                )
            await scraper.close()
            return
        mode_label = f"last {len(sample_dates)} BUSY weekdays (skipped empty days)"
    else:
        sample_dates = random_swim_season_dates(year, count)
        mode_label = f"{len(sample_dates)} random swim-season dates from {year}"

    if not sample_dates:
        logger.error(f"No dates found (year={year}, recent={recent})")
        await scraper.close()
        return

    logger.info(
        f"QC: {mode_label} ({sample_dates[0]} to {sample_dates[-1]})"
    )
    results = []
    try:
        for d in sample_dates:
            d_str = d.strftime("%Y-%m-%d")

            # Pull DB ids for this date
            async with get_db_context() as db:
                rows = (await db.execute(
                    select(Inspection.inspection_id).where(Inspection.inspection_date == d)
                )).all()
                db_ids = {r[0].upper() for r in rows if r[0]}

            # Pull portal ids
            try:
                facilities = await scraper.scrape_date_range(d_str, d_str, max_load_more=30)
            except PortalBlocked as e:
                logger.error(f"ABORTING: {e}")
                if alert_on_mismatch:
                    from _notify import alert_failure
                    alert_failure(
                        "inspection QC",
                        f"QC blocked mid-run by portal WAF (403/429) on {d_str}.\n{e}\n\nProcessed {len(results)} dates before block. Investigate cumulative request volume if persistent.",
                        cooldown_seconds=6 * 3600,
                    )
                break
            except Exception as e:
                logger.warning(f"  {d_str}: scrape error: {e}")
                results.append({"date": d_str, "status": "ERROR", "detail": str(e)})
                continue

            portal_ids = {f["inspection_id"].upper() for f in facilities if f.get("inspection_id")}

            both = db_ids & portal_ids
            db_only = db_ids - portal_ids
            portal_only = portal_ids - db_ids

            # ALERT POLICY: only "portal_only" is actionable drift — those
            # are inspections the portal currently shows that we don't have.
            # "db_only" is records we kept which the portal hides via its
            # listing collapse (multi-BoW siblings, deprecated leads); that's
            # noise we already understand and explicitly decided to keep.
            status = "OK" if not portal_only else "MISMATCH"
            mark = "✓" if status == "OK" else "✗"
            logger.info(
                f"  {d_str}  {mark}  db={len(db_ids):3d}  portal={len(portal_ids):3d}  "
                f"both={len(both):3d}  db_only={len(db_only):2d}  portal_only={len(portal_only):2d}"
            )

            results.append({
                "date": d_str,
                "status": status,
                "db": len(db_ids),
                "portal": len(portal_ids),
                "both": len(both),
                "db_only": list(db_only),
                "portal_only": list(portal_only),
            })
    finally:
        await scraper.close()

    # Summary
    ok = sum(1 for r in results if r["status"] == "OK")
    mismatch = sum(1 for r in results if r["status"] == "MISMATCH")
    err = sum(1 for r in results if r["status"] == "ERROR")
    logger.info("\n=== QC SUMMARY ===")
    logger.info(f"  OK:        {ok}/{len(results)}")
    logger.info(f"  MISMATCH:  {mismatch}/{len(results)}")
    logger.info(f"  ERROR:     {err}/{len(results)}")

    if mismatch:
        logger.info("\n=== MISMATCH DETAIL ===")
        for r in results:
            if r["status"] != "MISMATCH":
                continue
            logger.info(f"  {r['date']}: db={r['db']} portal={r['portal']}")
            if r["db_only"]:
                logger.info(f"    DB-only ({len(r['db_only'])}): {r['db_only'][:5]}{'...' if len(r['db_only']) > 5 else ''}")
            if r["portal_only"]:
                logger.info(f"    Portal-only ({len(r['portal_only'])}): {r['portal_only'][:5]}{'...' if len(r['portal_only']) > 5 else ''}")

    # ntfy alert on mismatch (when --alert was passed, e.g. via cron)
    if alert_on_mismatch and (mismatch > 0 or err > 0):
        from _notify import alert_failure
        details = "\n".join(
            f"{r['date']}: db={r.get('db','?')} portal={r.get('portal','?')}"
            f" db_only={len(r.get('db_only',[]))} portal_only={len(r.get('portal_only',[]))}"
            for r in results if r["status"] != "OK"
        )
        body = f"QC: {ok} OK / {mismatch} mismatch / {err} error\n\n{details}"
        alert_failure("inspection QC", body, cooldown_seconds=3600)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=10, help="Number of dates (default 10)")
    p.add_argument("--year", type=int, default=None,
                   help="Year to sample for swim-season mode. Default = current year if today is in swim season, else previous year.")
    p.add_argument("--recent", action="store_true",
                   help="Recency mode: walk back from today, only count days with actual inspection activity. Skips empty days.")
    p.add_argument("--alert", action="store_true",
                   help="Send a ntfy alert on mismatch/error (for cron use)")
    args = p.parse_args()
    year = args.year if args.year is not None else smart_default_year()
    asyncio.run(main(year=year, count=args.count, recent=args.recent, alert_on_mismatch=args.alert))
