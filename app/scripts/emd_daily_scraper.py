#!/usr/bin/env python3
"""EMD Daily Scraper — automated daily scraping of new inspections.

Runs as a systemd service. Scrapes today's and yesterday's inspections every day,
downloads PDFs, extracts data. Includes health monitoring, retry logic, and
notification on persistent failure.

Health status written to /tmp/emd_scraper_health.json for monitoring.
"""

import asyncio
import json
import os
import sys
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

HEALTH_FILE = "/tmp/emd_scraper_health.json"
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "emd")
SCRAPE_HOUR = 20  # 8 PM — after most inspections for the day
RETRY_INTERVAL_MINUTES = 30
MAX_CONSECUTIVE_FAILURES = 6  # 3 hours of failures before alerting
RATE_LIMIT_SECONDS = 8


def load_health() -> dict:
    try:
        with open(HEALTH_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "state": "starting",
            "last_success": None,
            "last_attempt": None,
            "last_error": None,
            "consecutive_failures": 0,
            "total_scrapes": 0,
            "total_inspections_found": 0,
            "total_pdfs_downloaded": 0,
            "alert_sent": False,
        }


def save_health(health: dict):
    health["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(HEALTH_FILE, "w") as f:
        json.dump(health, f, indent=2, default=str)


async def send_alert(message: str, health: dict):
    """Send alert via ntfy + write a local marker file for off-device checks."""
    logger.critical(f"SCRAPER ALERT: {message}")
    from _notify import alert_failure
    body = (
        f"{message}\n\n"
        f"consecutive_failures: {health.get('consecutive_failures', 0)}\n"
        f"last_success: {health.get('last_success')}\n"
        f"last_attempt: {health.get('last_attempt')}\n"
    )
    alert_failure("inspection scraper", body, cooldown_seconds=3600)

    # Also keep a local marker file for offline inspection
    alert_file = "/tmp/emd_scraper_alert.json"
    alert = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "health": health,
    }
    with open(alert_file, "w") as f:
        json.dump(alert, f, indent=2, default=str)


async def scrape_day(target_date: date) -> dict:
    """Scrape a single day's inspections and download PDFs."""
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from src.services.inspection.scraper import PortalBlocked
    from src.services.emd.service import EMDService
    from src.services.emd.pdf_extractor import EMDPDFExtractor
    from src.models.emd_inspection import EMDInspection
    from sqlalchemy import select

    scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT_SECONDS)
    extractor = EMDPDFExtractor()
    date_str = target_date.strftime("%Y-%m-%d")
    result = {"date": date_str, "found": 0, "new": 0, "pdfs": 0, "failed": 0, "errors": []}

    try:
        facilities = await scraper.scrape_date_range(date_str, date_str, max_load_more=20)
        result["found"] = len(facilities)
        logger.info(f"  {date_str}: found {len(facilities)} inspections")

        if not facilities:
            return result

        async with get_db_context() as db:
            svc = EMDService(db)

            for fdata in facilities:
                try:
                    inspection_id = fdata.get("inspection_id")
                    if not inspection_id:
                        continue

                    # Check if already exists
                    existing = await db.execute(
                        select(EMDInspection).where(EMDInspection.inspection_id == inspection_id)
                    )
                    existing_record = existing.scalar_one_or_none()

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
                                result["pdfs"] += 1
                                # Update existing record's PDF path if needed
                                if existing_record and existing_record.pdf_path != pdf_path:
                                    existing_record.pdf_path = pdf_path
                                    # Re-extract
                                    data = extractor.extract_all(pdf_path)
                                    if data.get("permit_id"):
                                        existing_record.permit_id = data["permit_id"]
                                    if data.get("program_identifier"):
                                        existing_record.program_identifier = data["program_identifier"]
                            else:
                                result["failed"] += 1
                                pdf_path = None
                        else:
                            result["pdfs"] += 1  # Already on disk

                    if existing_record:
                        continue

                    # New inspection — save to DB
                    save_result = await svc.process_facility(fdata, pdf_path=pdf_path)
                    if save_result in ("new_facility", "new_inspection"):
                        result["new"] += 1

                        # If PDF was downloaded, extract permit_id
                        if pdf_path and os.path.exists(pdf_path):
                            insp_record = await db.execute(
                                select(EMDInspection).where(EMDInspection.inspection_id == inspection_id)
                            )
                            insp = insp_record.scalar_one_or_none()
                            if insp:
                                data = extractor.extract_all(pdf_path)
                                if data.get("permit_id"):
                                    insp.permit_id = data["permit_id"]
                                if data.get("program_identifier"):
                                    insp.program_identifier = data["program_identifier"]

                except Exception as e:
                    result["errors"].append(str(e))
                    logger.warning(f"  Error processing {fdata.get('name', '?')}: {e}")

                await asyncio.sleep(RATE_LIMIT_SECONDS)

            # Auto-match new facilities
            if result["new"] > 0:
                try:
                    # Get first org for auto-matching
                    from src.models.organization import Organization
                    org_result = await db.execute(select(Organization).limit(1))
                    org = org_result.scalar_one_or_none()
                    if org:
                        match_result = await svc.auto_match_facilities(org.id)
                        if match_result.get("matched", 0) > 0:
                            logger.info(f"  Auto-matched {match_result['matched']} facilities")
                except Exception as e:
                    logger.warning(f"  Auto-match error: {e}")

        # --- Walk every permit URL we just saw to catch multi-BoW siblings ---
        # The portal's date-search listing collapses multiple inspections at the
        # same facility on the same day to one row. The permit page lists every
        # inspection. Walk each permit and ingest any sibling we don't have.
        seen_permit_urls = {f.get("url") for f in facilities if f.get("url")}
        result["sibling_new"] = 0
        for permit_url in seen_permit_urls:
            try:
                listed = await scraper.get_permit_inspections(permit_url)
            except PortalBlocked as e:
                logger.error(f"  ABORTING permit walks: {e}")
                result["errors"].append(f"PortalBlocked: {e}")
                break
            except Exception as e:
                logger.warning(f"  permit walk failed for {permit_url}: {e}")
                continue

            for sibling in listed:
                sib_iid = sibling.get("inspection_id")
                sib_date = sibling.get("inspection_date")
                if not sib_iid or sib_date != date_str:
                    continue

                async with get_db_context() as db:
                    check = await db.execute(
                        select(EMDInspection).where(EMDInspection.inspection_id == sib_iid)
                    )
                    if check.scalar_one_or_none():
                        continue  # Already have it

                # New sibling — download PDF and ingest
                sib_pdf_path = None
                sib_pdf_url = sibling.get("pdf_url")
                if sib_pdf_url:
                    try:
                        year_dir = os.path.join(UPLOADS_DIR, target_date.strftime("%Y"))
                        os.makedirs(year_dir, exist_ok=True)
                        sib_pdf_path = os.path.join(year_dir, f"{sib_iid}.pdf")
                        if not os.path.exists(sib_pdf_path):
                            ok = await scraper.download_pdf(sib_pdf_url, sib_pdf_path)
                            if ok and os.path.exists(sib_pdf_path) and os.path.getsize(sib_pdf_path) > 100:
                                result["pdfs"] += 1
                            else:
                                sib_pdf_path = None
                    except PortalBlocked as e:
                        logger.error(f"  ABORTING permit walks: {e}")
                        result["errors"].append(f"PortalBlocked: {e}")
                        return result
                    except Exception as e:
                        logger.warning(f"  sibling PDF download failed for {sib_iid}: {e}")
                        sib_pdf_path = None

                async with get_db_context() as db:
                    svc2 = EMDService(db)
                    try:
                        # Pull facility name from one of the original facilities sharing this permit URL
                        fname = next((f.get("name", "") for f in facilities if f.get("url") == permit_url), "")
                        sib_fdata = {
                            "name": fname,
                            "address": "",
                            "url": permit_url,
                            "pdf_url": sib_pdf_url,
                            "inspection_id": sib_iid,
                            "inspection_date": sib_date,
                        }
                        save_result = await svc2.process_facility(sib_fdata, pdf_path=sib_pdf_path)
                        if save_result in ("new_inspection", "new_facility"):
                            result["sibling_new"] += 1
                            result["new"] += 1
                        await db.commit()
                    except Exception as e:
                        logger.warning(f"  sibling process_facility failed for {sib_iid}: {e}")
                        await db.rollback()
                        result["errors"].append(f"sibling {sib_iid}: {e}")

                # No manual sleep here — scraper._request enforces rate limit internally

        if result["sibling_new"]:
            logger.info(f"  {date_str}: caught {result['sibling_new']} multi-BoW siblings via permit walking")

    finally:
        await scraper.close()

    return result


async def run_daily_scrape():
    """Run the daily scrape cycle."""
    from src.core.database import get_db_context
    from src.models.scraper_run import ScraperRun

    health = load_health()
    health["state"] = "scraping"
    health["last_attempt"] = datetime.now(timezone.utc).isoformat()
    save_health(health)

    today = date.today()
    yesterday = today - timedelta(days=1)
    start_time = datetime.now(timezone.utc)
    all_errors = []

    try:
        total_found = 0
        total_new = 0
        total_pdfs = 0

        for target in [yesterday, today]:
            logger.info(f"Scraping {target}...")
            result = await scrape_day(target)
            total_found += result["found"]
            total_new += result["new"]
            total_pdfs += result["pdfs"]
            all_errors.extend(result.get("errors", []))

            if result["errors"]:
                logger.warning(f"  {len(result['errors'])} errors on {target}")

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Success
        health["state"] = "idle"
        health["last_success"] = datetime.now(timezone.utc).isoformat()
        health["consecutive_failures"] = 0
        health["alert_sent"] = False
        health["total_scrapes"] += 1
        health["total_inspections_found"] += total_found
        health["total_pdfs_downloaded"] += total_pdfs
        save_health(health)

        logger.info(f"Daily scrape complete: found={total_found}, new={total_new}, pdfs={total_pdfs}")

        # Log to DB
        try:
            async with get_db_context() as db:
                run = ScraperRun(
                    started_at=start_time,
                    finished_at=datetime.now(timezone.utc),
                    status="success",
                    days_scraped=2,
                    inspections_found=total_found,
                    inspections_new=total_new,
                    pdfs_downloaded=total_pdfs,
                    errors="\n".join(all_errors) if all_errors else None,
                    duration_seconds=duration,
                )
                db.add(run)
                # email_sent is a vestigial column from the SMTP era — set to
                # False since we now use ntfy for failures only (no per-run
                # success email).
                run.email_sent = False

                await db.commit()
        except Exception as e:
            logger.error(f"Failed to log scraper run: {e}")

        # Notify on partial failures (run succeeded overall but some
        # inspections errored). The send_alert path is only for hard failures.
        if all_errors:
            from _notify import send_ntfy
            send_ntfy(
                title="QP inspection scraper: partial errors",
                body=f"Daily scrape ran but {len(all_errors)} inspection(s) errored.\nFirst few:\n" + "\n".join(all_errors[:5]),
                priority="default",
                tags="warning",
                cooldown_key="scraper_partial_errors",
                cooldown_seconds=3600,
            )

    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        health["state"] = "error"
        health["last_error"] = str(e)
        health["consecutive_failures"] += 1
        save_health(health)

        logger.error(f"Daily scrape failed: {e}")

        # Log failure to DB
        try:
            async with get_db_context() as db:
                run = ScraperRun(
                    started_at=start_time,
                    finished_at=datetime.now(timezone.utc),
                    status="error",
                    errors=str(e),
                    duration_seconds=duration,
                )
                db.add(run)
                await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to log scraper error: {db_err}")

        # PortalBlocked is severe — alert IMMEDIATELY (with long cooldown so a
        # multi-hour WAF window doesn't spam). Other generic errors wait for
        # MAX_CONSECUTIVE_FAILURES so we don't alert on a single transient blip.
        is_portal_blocked = "PortalBlocked" in type(e).__name__ or "Circuit breaker" in str(e) or "403" in str(e) or "429" in str(e)
        if is_portal_blocked:
            from _notify import alert_failure
            alert_failure(
                "inspection scraper",
                f"Daily scraper blocked by portal WAF (403/429).\n{e}\n\nThe portal block typically clears within 24h. Investigate cumulative request volume if persistent across multiple runs.",
                cooldown_seconds=6 * 3600,
            )
        elif health["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES and not health["alert_sent"]:
            await send_alert(
                f"EMD scraper has failed {health['consecutive_failures']} consecutive times. "
                f"Last error: {e}",
                health,
            )
            health["alert_sent"] = True
            save_health(health)


async def main():
    """Main loop — runs daily scrape on schedule, retries on failure."""
    health = load_health()
    health["state"] = "idle"
    health["started_at"] = datetime.now(timezone.utc).isoformat()
    save_health(health)

    logger.info("EMD Daily Scraper started")
    logger.info(f"  Schedule: daily at {SCRAPE_HOUR}:00")
    logger.info(f"  Retry interval: {RETRY_INTERVAL_MINUTES}min")
    logger.info(f"  Alert after: {MAX_CONSECUTIVE_FAILURES} consecutive failures")

    while True:
        now = datetime.now()
        health = load_health()

        # Check if we need to scrape
        should_scrape = False

        if health.get("last_success"):
            last_success = datetime.fromisoformat(health["last_success"])
            hours_since = (datetime.now(timezone.utc) - last_success).total_seconds() / 3600

            if hours_since > 24:
                should_scrape = True
            elif health["state"] == "error" and health["consecutive_failures"] < MAX_CONSECUTIVE_FAILURES:
                # Retry after interval
                if health.get("last_attempt"):
                    last_attempt = datetime.fromisoformat(health["last_attempt"])
                    mins_since = (datetime.now(timezone.utc) - last_attempt).total_seconds() / 60
                    if mins_since >= RETRY_INTERVAL_MINUTES:
                        should_scrape = True
        else:
            # Never succeeded — scrape now
            should_scrape = True

        # Also scrape at scheduled hour if we haven't today
        if now.hour == SCRAPE_HOUR:
            if health.get("last_success"):
                last = datetime.fromisoformat(health["last_success"])
                if last.date() < now.date():
                    should_scrape = True
            else:
                should_scrape = True

        if should_scrape:
            await run_daily_scrape()

        # Sleep 5 minutes between checks
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
