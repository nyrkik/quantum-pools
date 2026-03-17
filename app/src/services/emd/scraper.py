"""EMD Website Scraper — Playwright async port of the original Selenium-based Pool Scout Pro scraper.

Navigates to Sacramento County's myhealthdepartment.com inspection portal,
filters by date range, extracts facility listings and inspection PDF URLs.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

EMD_URL = "https://inspections.myhealthdepartment.com/sacramento/program-rec-health"
DEFAULT_RATE_LIMIT = 5  # seconds between requests


class EMDScraper:
    """Playwright-based scraper for Sacramento County EMD inspection portal."""

    def __init__(self, rate_limit_seconds: int = DEFAULT_RATE_LIMIT):
        self.rate_limit_seconds = rate_limit_seconds
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self):
        """Launch Chromium browser if not already running."""
        if self._browser and self._browser.is_connected():
            return

        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        logger.info("Playwright browser launched")

    async def close(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright browser closed")

    async def scrape_date_range(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        max_load_more: int = 10,
    ) -> list[dict]:
        """Scrape EMD inspections for a date range.

        Args:
            start_date: YYYY-MM-DD format
            end_date: YYYY-MM-DD format (defaults to start_date)
            max_load_more: Maximum "Load more" clicks

        Returns:
            List of facility dicts with keys: name, address, url, pdf_url,
            inspection_id, inspection_date
        """
        if end_date is None:
            end_date = start_date

        await self._ensure_browser()
        page = await self._browser.new_page()

        try:
            # Format dates for the date picker: MM/DD/YYYY
            formatted_start = datetime.strptime(start_date, "%Y-%m-%d").strftime("%m/%d/%Y")
            formatted_end = datetime.strptime(end_date, "%Y-%m-%d").strftime("%m/%d/%Y")
            date_range = f"{formatted_start} to {formatted_end}"

            logger.info(f"Navigating to EMD portal for {start_date} to {end_date}")
            await page.goto(EMD_URL, wait_until="domcontentloaded", timeout=30000)

            # Wait for the date picker to be present
            await page.wait_for_selector(".alt-datePicker", timeout=15000)
            logger.info("Page loaded, date picker found")

            # Set date filter via JavaScript (same approach as the Selenium version)
            await page.eval_on_selector(
                ".alt-datePicker",
                """(el, dateRange) => {
                    el.value = '';
                    el.focus();
                    el.value = dateRange;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.blur();
                }""",
                date_range,
            )

            logger.info(f"Date filter set to: {date_range}")

            # Wait for results to load
            await asyncio.sleep(self.rate_limit_seconds)

            # Check for results
            results = await page.query_selector_all(".flex-row")
            if not results:
                logger.info("No results found for this date range")
                return []

            logger.info(f"Found {len(results)} initial results")

            # Handle "Load more" button
            await self._handle_load_more(page, max_load_more)

            # Extract facility data
            facilities = await self._extract_facilities(page, start_date)
            logger.info(f"Extracted {len(facilities)} facilities")

            # Deduplicate by inspection_id
            seen_ids = set()
            unique = []
            for f in facilities:
                iid = f.get("inspection_id")
                if iid and iid in seen_ids:
                    continue
                if iid:
                    seen_ids.add(iid)
                unique.append(f)

            logger.info(f"Returning {len(unique)} unique facilities (removed {len(facilities) - len(unique)} duplicates)")
            return unique

        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            raise
        finally:
            await page.close()

    async def _handle_load_more(self, page, max_attempts: int):
        """Click 'Load more' button until no more results or max attempts reached."""
        for attempt in range(max_attempts):
            buttons = await page.query_selector_all(".load-more-results-button")
            if not buttons:
                logger.info("No Load More button found")
                break

            button = buttons[0]
            is_visible = await button.is_visible()
            is_enabled = await button.is_enabled()

            if not is_visible or not is_enabled:
                logger.info("Load More button disabled or hidden")
                break

            current_count = len(await page.query_selector_all(".flex-row"))
            await button.click()
            logger.info(f"Load More clicked (attempt {attempt + 1}/{max_attempts})")

            await asyncio.sleep(self.rate_limit_seconds)

            new_count = len(await page.query_selector_all(".flex-row"))
            logger.info(f"Results: {current_count} -> {new_count}")

            if new_count <= current_count:
                logger.info("No new results loaded, stopping")
                break

    async def _extract_facilities(self, page, search_date: str) -> list[dict]:
        """Extract facility data from all .flex-row elements on the page."""
        facilities = []
        elements = await page.query_selector_all(".flex-row")

        for i, element in enumerate(elements):
            try:
                facility = await self._extract_single_facility(element, i, search_date)
                if facility:
                    facilities.append(facility)
            except Exception as e:
                logger.warning(f"Failed to extract facility {i}: {e}")
                continue

        return facilities

    async def _extract_single_facility(self, element, index: int, search_date: str) -> Optional[dict]:
        """Extract data from a single facility element."""
        # Get facility name and URL
        name_link = await element.query_selector("h4.establishment-list-name a")
        if not name_link:
            return None

        name = (await name_link.text_content() or "").strip()
        url = await name_link.get_attribute("href") or ""

        # Get address
        address_el = await element.query_selector(".establishment-list-address")
        address = (await address_el.text_content() or "Unknown").strip() if address_el else "Unknown"

        # Get PDF/inspection URL
        pdf_url = None
        inspection_id = None
        inspection_btn = await element.query_selector(".view-inspections-button")
        if inspection_btn:
            pdf_url = await inspection_btn.get_attribute("href")
            if pdf_url:
                inspection_id = self._extract_inspection_id(pdf_url)

        return {
            "name": name,
            "address": address,
            "url": url,
            "pdf_url": pdf_url,
            "inspection_id": inspection_id,
            "inspection_date": search_date,
        }

    @staticmethod
    def _extract_inspection_id(url: str) -> Optional[str]:
        """Extract UUID-style inspection ID from a URL."""
        match = re.search(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            url,
        )
        return match.group(1).upper() if match else None

    async def download_pdf(self, url: str, save_path: str) -> bool:
        """Download a PDF from the given URL.

        Args:
            url: PDF download URL
            save_path: Local path to save the file

        Returns:
            True if download succeeded
        """
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            response = await page.goto(url, timeout=30000)
            if response and response.ok:
                content = await response.body()
                if content and len(content) > 100:
                    import os
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(content)
                    logger.info(f"PDF downloaded: {save_path} ({len(content)} bytes)")
                    return True
            logger.warning(f"PDF download failed for {url}")
            return False
        except Exception as e:
            logger.error(f"PDF download error: {e}")
            return False
        finally:
            await page.close()

    async def get_facility_detail(self, facility_url: str) -> dict:
        """Navigate to a facility detail page and extract additional data.

        Returns dict with keys: permit_holder, phone, facility_id, facility_type, address_parts
        """
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto(facility_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            detail = {}

            # Try to extract structured data from the detail page
            info_items = await page.query_selector_all(".establishment-info-item")
            for item in info_items:
                label_el = await item.query_selector(".info-label")
                value_el = await item.query_selector(".info-value")
                if label_el and value_el:
                    label = (await label_el.text_content() or "").strip().lower()
                    value = (await value_el.text_content() or "").strip()
                    if "permit" in label and "holder" in label:
                        detail["permit_holder"] = value
                    elif "phone" in label:
                        detail["phone"] = value
                    elif "facility" in label and "id" in label:
                        detail["facility_id"] = value
                    elif "type" in label:
                        detail["facility_type"] = value

            return detail
        except Exception as e:
            logger.warning(f"Failed to get facility detail: {e}")
            return {}
        finally:
            await page.close()
