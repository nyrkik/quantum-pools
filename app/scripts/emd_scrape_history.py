#!/usr/bin/env python3
"""EMD History Scraper — finds all historical inspections via facility detail pages.

Strategy: for each facility with a known inspection, navigate to that inspection,
follow the facility link, scrape all inspection IDs from the facility detail page,
download PDFs for any we don't have.

Usage:
    python scripts/emd_scrape_history.py [--matched-only]
"""

import asyncio
import os
import re
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "emd")
RATE_LIMIT = 8
EMD_BASE = "https://inspections.myhealthdepartment.com"


async def get_facility_inspections(scraper, known_inspection_id: str) -> list[str]:
    """From a known inspection ID, navigate to facility page and return all inspection IDs."""
    await scraper._ensure_browser()
    context = await scraper._browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
    )
    page = await context.new_page()
    try:
        # Step 1: Go to known inspection
        insp_url = f"{EMD_BASE}/sacramento/program-rec-health/inspection/?inspectionID={known_inspection_id}"
        await page.goto(insp_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Step 2: Find facility link
        facility_link = await page.query_selector('a[href*="permit/?permitID"]')
        if not facility_link:
            return []

        href = await facility_link.get_attribute("href")
        facility_url = f"{EMD_BASE}{href}" if href.startswith("/") else href

        # Step 3: Navigate to facility detail page
        await page.goto(facility_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Step 4: Extract all inspection IDs
        html = await page.content()
        ids = set(re.findall(
            r"inspectionID=([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            html,
        ))
        return [iid.upper() for iid in ids]

    except Exception as e:
        logger.warning(f"Error getting facility inspections from {known_inspection_id}: {e}")
        return []
    finally:
        await page.close()
        await context.close()


async def main():
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from src.services.emd.service import EMDService
    from src.services.emd.pdf_extractor import EMDPDFExtractor
    from src.models.emd_facility import EMDFacility
    from src.models.emd_inspection import EMDInspection
    from sqlalchemy import select, func

    matched_only = "--matched-only" in sys.argv

    scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT)
    extractor = EMDPDFExtractor()
    new_inspections = 0
    new_pdfs = 0
    facilities_done = 0

    try:
        async with get_db_context() as db:
            # Get facilities that have at least one inspection (so we have a known ID to start from)
            query = (
                select(EMDFacility.id, EMDFacility.name, EMDFacility.facility_id)
                .join(EMDInspection, EMDInspection.facility_id == EMDFacility.id)
            )
            if matched_only:
                query = query.where(EMDFacility.matched_property_id.isnot(None))

            query = query.group_by(EMDFacility.id, EMDFacility.name, EMDFacility.facility_id).order_by(EMDFacility.name)
            result = await db.execute(query)
            facilities = result.all()
            logger.info(f"Facilities to check: {len(facilities)}")

            for idx, (fac_id, fac_name, fac_fa) in enumerate(facilities):
              try:
                # Get one known inspection ID for this facility
                known = await db.execute(
                    select(EMDInspection.inspection_id)
                    .where(EMDInspection.facility_id == fac_id, EMDInspection.inspection_id.isnot(None))
                    .limit(1)
                )
                known_id = known.scalar()
                if not known_id:
                    continue

                logger.info(f"[{idx+1}/{len(facilities)}] {fac_name} ({fac_fa})")

                # Get all inspection IDs from facility page
                all_ids = await get_facility_inspections(scraper, known_id)
                if not all_ids:
                    logger.info(f"  No inspections found on facility page")
                    continue

                # Check which ones we already have
                existing = await db.execute(
                    select(EMDInspection.inspection_id)
                    .where(EMDInspection.inspection_id.in_(all_ids))
                )
                existing_ids = {r.inspection_id for r in existing.all()}
                missing = [iid for iid in all_ids if iid not in existing_ids]

                if not missing:
                    logger.info(f"  {len(all_ids)} inspections, all present")
                    facilities_done += 1
                    continue

                logger.info(f"  {len(all_ids)} total, {len(missing)} missing")

                # Download and process missing inspections
                svc = EMDService(db)
                for iid in missing:
                    pdf_url = f"/sacramento/program-rec-health/inspection/?inspectionID={iid}"
                    year_dir = os.path.join(UPLOADS_DIR, "scraped")
                    os.makedirs(year_dir, exist_ok=True)
                    pdf_path = os.path.join(year_dir, f"{iid}.pdf")

                    if not os.path.exists(pdf_path):
                        success = await scraper.download_pdf(pdf_url, pdf_path)
                        if success and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
                            new_pdfs += 1
                        else:
                            logger.warning(f"  Failed to download {iid}")
                            pdf_path = None

                    if pdf_path and os.path.exists(pdf_path):
                        data = extractor.extract_all(pdf_path)

                        # Move to correct year dir
                        insp_date = None
                        if data.get("inspection_date"):
                            try:
                                from datetime import datetime
                                insp_date = datetime.strptime(data["inspection_date"], "%Y-%m-%d").date()
                                correct_dir = os.path.join(UPLOADS_DIR, str(insp_date.year))
                                os.makedirs(correct_dir, exist_ok=True)
                                correct_path = os.path.join(correct_dir, f"{iid}.pdf")
                                if correct_path != pdf_path and not os.path.exists(correct_path):
                                    os.rename(pdf_path, correct_path)
                                    pdf_path = correct_path
                            except (ValueError, TypeError):
                                pass

                        facility_data = {
                            "name": fac_name,
                            "facility_id": fac_fa,
                            "inspection_id": iid,
                            "inspection_date": data.get("inspection_date"),
                        }
                        await svc.process_facility(facility_data, pdf_path=pdf_path)

                        # Update permit_id and program_identifier
                        insp_record = await db.execute(
                            select(EMDInspection).where(EMDInspection.inspection_id == iid)
                        )
                        insp = insp_record.scalar_one_or_none()
                        if insp:
                            if data.get("permit_id"):
                                insp.permit_id = data["permit_id"]
                            if data.get("program_identifier"):
                                insp.program_identifier = data["program_identifier"]
                            else:
                                insp.program_identifier = "POOL"

                        new_inspections += 1
                        logger.info(f"  NEW: {iid} date={data.get('inspection_date')} prog={data.get('program_identifier')}")

                    await asyncio.sleep(RATE_LIMIT)

                await db.flush()
                facilities_done += 1

                if (idx + 1) % 20 == 0:
                    logger.info(f"  Progress: {idx+1}/{len(facilities)}, {new_inspections} new, {new_pdfs} PDFs")

              except Exception as e:
                logger.error(f"  Error processing {fac_name}: {e}")
                # Rollback to clean state for next facility
                try:
                    await db.rollback()
                except Exception:
                    pass

    finally:
        await scraper.close()

    logger.info(f"\nDone. Facilities: {facilities_done} | New inspections: {new_inspections} | PDFs: {new_pdfs}")


if __name__ == "__main__":
    asyncio.run(main())
