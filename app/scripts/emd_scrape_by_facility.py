#!/usr/bin/env python3
"""EMD Facility History Scraper — scrapes all inspections for each known facility.

Instead of scraping by date (which misses older inspections), this navigates to
each facility's page on the EMD portal and pulls all historical inspections.

Usage:
    nohup python scripts/emd_scrape_by_facility.py > /tmp/emd_facility_scrape.log 2>&1 &
"""

import asyncio
import os
import sys
import logging
import re
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "emd")
RATE_LIMIT = 8
EMD_BASE = "https://inspections.myhealthdepartment.com"


async def scrape_facility_inspections(scraper, facility_id_emd: str) -> list[dict]:
    """Navigate to a facility's page and extract all inspection links."""
    await scraper._ensure_browser()

    # Search for the facility by its FA number
    search_url = f"{EMD_BASE}/sacramento/program-rec-health?searchText={facility_id_emd}"

    context = await scraper._browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
    )
    page = await context.new_page()

    inspections = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Click on the facility to go to its detail/inspection list
        facility_link = await page.query_selector(f'a:has-text("{facility_id_emd}")')
        if not facility_link:
            # Try finding any establishment link
            facility_link = await page.query_selector(".establishment-list-name a")

        if not facility_link:
            logger.warning(f"  Could not find facility link for {facility_id_emd}")
            return []

        await facility_link.click()
        await asyncio.sleep(3)

        # Now on facility page — find all inspection links
        # Look for inspection rows/buttons
        insp_buttons = await page.query_selector_all(".view-inspections-button, .inspection-row a, [href*='inspection']")

        for btn in insp_buttons:
            href = await btn.get_attribute("href") or ""
            if "inspectionID" not in href and "inspection" not in href.lower():
                continue

            # Extract inspection ID
            match = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", href)
            if match:
                insp_id = match.group(1).upper()
                inspections.append({
                    "inspection_id": insp_id,
                    "pdf_url": href,
                })

        # If no inspection buttons found, try the inspection list section
        if not inspections:
            # Some facility pages list inspections differently
            all_links = await page.query_selector_all("a")
            for link in all_links:
                href = await link.get_attribute("href") or ""
                match = re.search(r"inspectionID=([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", href)
                if match:
                    insp_id = match.group(1).upper()
                    if not any(i["inspection_id"] == insp_id for i in inspections):
                        inspections.append({
                            "inspection_id": insp_id,
                            "pdf_url": href,
                        })

    except Exception as e:
        logger.warning(f"  Error scraping {facility_id_emd}: {e}")
    finally:
        await page.close()
        await context.close()

    return inspections


async def main():
    from src.core.database import get_db_context
    from src.services.emd.scraper import EMDScraper
    from src.services.emd.pdf_extractor import EMDPDFExtractor
    from src.models.emd_facility import EMDFacility
    from src.models.emd_inspection import EMDInspection
    from sqlalchemy import select, func

    scraper = EMDScraper(rate_limit_seconds=RATE_LIMIT)
    extractor = EMDPDFExtractor()

    new_inspections = 0
    new_pdfs = 0
    facilities_scraped = 0
    errors = 0

    try:
        async with get_db_context() as db:
            # Get all facilities with FA numbers
            result = await db.execute(
                select(EMDFacility)
                .where(EMDFacility.facility_id.isnot(None))
                .order_by(EMDFacility.name)
            )
            facilities = result.scalars().all()
            logger.info(f"Facilities to scrape: {len(facilities)}")

            for idx, fac in enumerate(facilities):
                logger.info(f"[{idx+1}/{len(facilities)}] {fac.name} ({fac.facility_id})")

                try:
                    found = await scrape_facility_inspections(scraper, fac.facility_id)
                    logger.info(f"  Found {len(found)} inspection links")

                    for insp_data in found:
                        insp_id = insp_data["inspection_id"]

                        # Check if already exists
                        existing = await db.execute(
                            select(EMDInspection).where(EMDInspection.inspection_id == insp_id)
                        )
                        if existing.scalar_one_or_none():
                            continue

                        # Download PDF
                        pdf_url = insp_data["pdf_url"]
                        year_dir = os.path.join(UPLOADS_DIR, "scraped")
                        os.makedirs(year_dir, exist_ok=True)
                        pdf_path = os.path.join(year_dir, f"{insp_id}.pdf")

                        if not os.path.exists(pdf_path):
                            success = await scraper.download_pdf(pdf_url, pdf_path)
                            if success and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
                                new_pdfs += 1
                            else:
                                pdf_path = None

                        if pdf_path and os.path.exists(pdf_path):
                            # Extract data from PDF
                            data = extractor.extract_all(pdf_path)

                            insp_date = None
                            if data.get("inspection_date"):
                                try:
                                    insp_date = datetime.strptime(data["inspection_date"], "%Y-%m-%d").date()
                                except (ValueError, TypeError):
                                    pass

                            # Move to correct year dir
                            if insp_date:
                                correct_dir = os.path.join(UPLOADS_DIR, str(insp_date.year))
                                os.makedirs(correct_dir, exist_ok=True)
                                correct_path = os.path.join(correct_dir, f"{insp_id}.pdf")
                                if correct_path != pdf_path:
                                    os.rename(pdf_path, correct_path)
                                    pdf_path = correct_path

                            from src.services.emd.service import EMDService
                            svc = EMDService(db)

                            facility_data = {
                                "name": fac.name,
                                "facility_id": fac.facility_id,
                                "inspection_id": insp_id,
                                "inspection_date": data.get("inspection_date"),
                            }
                            result_type = await svc.process_facility(facility_data, pdf_path=pdf_path)

                            # Update permit_id and program_identifier
                            insp_record = await db.execute(
                                select(EMDInspection).where(EMDInspection.inspection_id == insp_id)
                            )
                            insp_obj = insp_record.scalar_one_or_none()
                            if insp_obj:
                                if data.get("permit_id"):
                                    insp_obj.permit_id = data["permit_id"]
                                if data.get("program_identifier"):
                                    insp_obj.program_identifier = data["program_identifier"]

                            new_inspections += 1
                            logger.info(f"  NEW: {insp_id} date={data.get('inspection_date')} prog={data.get('program_identifier')}")

                    await db.flush()
                    facilities_scraped += 1

                except Exception as e:
                    logger.error(f"  Error: {e}")
                    errors += 1

                await asyncio.sleep(RATE_LIMIT)

                if (idx + 1) % 50 == 0:
                    logger.info(f"  Progress: {idx+1}/{len(facilities)} scraped, {new_inspections} new, {new_pdfs} PDFs, {errors} errors")

    finally:
        await scraper.close()

    logger.info(f"\nDone. Facilities: {facilities_scraped} | New inspections: {new_inspections} | PDFs: {new_pdfs} | Errors: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
