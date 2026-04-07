"""Inspection Portal Scraper — Playwright-based scraper for health department portals.

Supports any county that uses the myhealthdepartment.com platform (or similar).
County-specific behavior is configured via CountyConfig dataclass.

Default: Sacramento County EMD inspection portal.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from src.services.inspection.county_config import CountyConfig, SACRAMENTO

logger = logging.getLogger(__name__)


class InspectionScraper:
    """Playwright-based scraper for health department inspection portals.

    Accepts a CountyConfig to handle county-specific quirks (URL, selectors,
    date handling). Defaults to Sacramento County.
    """

    def __init__(self, config: CountyConfig | None = None, rate_limit_seconds: int | None = None):
        self.config = config or SACRAMENTO
        self.rate_limit_seconds = rate_limit_seconds or self.config.default_rate_limit_seconds
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self):
        """Launch browser if not already running."""
        if self._browser and self._browser.is_connected():
            return

        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        if self.config.use_firefox:
            self._browser = await self._playwright.firefox.launch(headless=True)
        else:
            self._browser = await self._playwright.chromium.launch(headless=True)
        logger.info(f"Playwright browser launched for {self.config.county_name}")

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
        max_load_more: int | None = None,
    ) -> list[dict]:
        """Scrape inspections for a date range.

        Args:
            start_date: YYYY-MM-DD format
            end_date: YYYY-MM-DD format (defaults to start_date)
            max_load_more: Maximum "Load more" clicks (defaults to config)

        Returns:
            List of facility dicts with keys: name, address, url, pdf_url,
            inspection_id, inspection_date
        """
        if end_date is None:
            end_date = start_date
        if max_load_more is None:
            max_load_more = self.config.max_load_more_clicks

        cfg = self.config
        await self._ensure_browser()
        context = await self._browser.new_context(
            user_agent=cfg.user_agent,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        page = await context.new_page()

        try:
            formatted_start = datetime.strptime(start_date, "%Y-%m-%d").strftime(cfg.date_input_format)
            formatted_end = datetime.strptime(end_date, "%Y-%m-%d").strftime(cfg.date_input_format)
            date_range = f"{formatted_start}{cfg.date_range_separator}{formatted_end}"

            logger.info(f"Navigating to {cfg.county_name} portal for {start_date} to {end_date}")
            await page.goto(cfg.portal_url, wait_until="domcontentloaded", timeout=cfg.page_load_timeout_ms)
            await page.wait_for_selector(cfg.date_picker_selector, timeout=cfg.selector_timeout_ms)
            logger.info("Page loaded, date picker found")

            # Set date filter
            success = await self._set_date_filter(page, date_range, formatted_start)
            if not success:
                return []

            # Check for results
            results = await page.query_selector_all(cfg.results_row_selector)
            if not results:
                logger.info("No results found for this date range")
                return []

            logger.info(f"Found {len(results)} initial results")

            # Extract results (with Load More safety net if configured)
            if cfg.extract_before_load_more:
                facilities = await self._extract_facilities(page, start_date)
                had_load_more = await self._handle_load_more(page, max_load_more)
                if had_load_more:
                    post_load = await self._extract_facilities(page, start_date)
                    if len(post_load) >= len(facilities):
                        facilities = post_load
                    else:
                        logger.warning(f"Load More reduced results ({len(facilities)} -> {len(post_load)}), keeping pre-Load More data")
            else:
                await self._handle_load_more(page, max_load_more)
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
            await context.close()

    async def _set_date_filter(self, page, date_range: str, expected_value: str) -> bool:
        """Set the date filter on the portal. Returns True if successful."""
        cfg = self.config

        if cfg.use_keyboard_date_input:
            return await self._set_date_keyboard(page, date_range, expected_value)
        else:
            return await self._set_date_js(page, date_range)

    async def _set_date_keyboard(self, page, date_range: str, expected_value: str) -> bool:
        """Set date via native keyboard input with retry (robust but slow)."""
        cfg = self.config
        picker = page.locator(cfg.date_picker_selector)

        for attempt in range(3):
            await picker.click(click_count=3)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)
            await picker.type(date_range, delay=50)
            await asyncio.sleep(0.3)
            await page.keyboard.press("Enter")
            await asyncio.sleep(self.rate_limit_seconds)

            current_val = await picker.input_value()
            if expected_value in current_val:
                logger.info(f"Date filter set to: {current_val} (attempt {attempt + 1})")
                return True

            logger.warning(f"Date filter didn't take (got '{current_val}'), retrying ({attempt + 1}/3)")
            await asyncio.sleep(self.rate_limit_seconds)
            try:
                await page.goto(cfg.portal_url, wait_until="domcontentloaded", timeout=cfg.page_load_timeout_ms)
                await page.wait_for_selector(cfg.date_picker_selector, timeout=cfg.selector_timeout_ms)
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Page reload failed on retry: {e}")
                continue

        logger.error("Date filter failed after 3 attempts, aborting")
        return False

    async def _set_date_js(self, page, date_range: str) -> bool:
        """Set date via JavaScript injection (faster but less robust)."""
        cfg = self.config
        try:
            await page.eval_on_selector(
                cfg.date_picker_selector,
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
            await asyncio.sleep(self.rate_limit_seconds)
            return True
        except Exception as e:
            logger.error(f"JS date injection failed: {e}")
            return False

    async def _handle_load_more(self, page, max_attempts: int) -> bool:
        """Click 'Load more' button until no more results or max attempts reached."""
        cfg = self.config
        clicked = False

        for attempt in range(max_attempts):
            buttons = await page.query_selector_all(cfg.load_more_selector)
            if not buttons:
                break

            button = buttons[0]
            if not await button.is_visible() or not await button.is_enabled():
                break

            current_count = len(await page.query_selector_all(cfg.results_row_selector))
            await button.click()
            clicked = True
            logger.info(f"Load More clicked (attempt {attempt + 1}/{max_attempts})")

            await asyncio.sleep(self.rate_limit_seconds)

            new_count = len(await page.query_selector_all(cfg.results_row_selector))
            logger.info(f"Results: {current_count} -> {new_count}")

            if new_count <= current_count:
                break

        return clicked

    async def _extract_facilities(self, page, search_date: str) -> list[dict]:
        """Extract facility data from all result elements on the page."""
        cfg = self.config
        facilities = []
        elements = await page.query_selector_all(cfg.results_row_selector)

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
        cfg = self.config

        name_link = await element.query_selector(cfg.facility_name_selector)
        if not name_link:
            return None

        name = (await name_link.text_content() or "").strip()
        url = await name_link.get_attribute("href") or ""

        address_el = await element.query_selector(cfg.address_selector)
        address = (await address_el.text_content() or "Unknown").strip() if address_el else "Unknown"

        # Get inspection date — from HTML if configured, otherwise use search date
        inspection_date = search_date
        if cfg.parse_date_from_results:
            date_divs = await element.query_selector_all(cfg.date_display_selector)
            for div in date_divs:
                text = (await div.text_content() or "").strip()
                parsed = self._parse_inspection_date(text)
                if parsed:
                    inspection_date = parsed
                    break

        # Get PDF/inspection URL
        pdf_url = None
        inspection_id = None
        inspection_btn = await element.query_selector(cfg.inspection_button_selector)
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
            "inspection_date": inspection_date,
        }

    @staticmethod
    def _parse_inspection_date(text: str) -> Optional[str]:
        """Parse date like 'March 26, 2026' from result text, return YYYY-MM-DD."""
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})",
            text,
        )
        if match:
            try:
                return datetime.strptime(match.group(0), "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None

    @staticmethod
    def _extract_inspection_id(url: str) -> Optional[str]:
        """Extract UUID-style inspection ID from a URL."""
        match = re.search(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            url,
        )
        return match.group(1).upper() if match else None

    async def download_pdf(self, inspection_url: str, save_path: str) -> bool:
        """Download inspection PDF via two-step process."""
        cfg = self.config
        full_url = (cfg.base_url + inspection_url) if inspection_url.startswith("/") else inspection_url

        await self._ensure_browser()
        context = await self._browser.new_context(
            user_agent=cfg.user_agent,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        page = await context.new_page()
        try:
            logger.info(f"Navigating to inspection page: {full_url}")
            await page.goto(full_url, timeout=cfg.page_load_timeout_ms, wait_until="domcontentloaded")

            try:
                await page.wait_for_selector(cfg.pdf_link_selector, timeout=cfg.selector_timeout_ms)
            except Exception:
                await asyncio.sleep(5)

            pdf_link = await page.query_selector(cfg.pdf_link_selector)
            if not pdf_link:
                pdf_link = await page.query_selector(cfg.pdf_link_fallback_selector)
            if not pdf_link:
                logger.warning(f"No PDF link found on inspection page: {full_url}")
                return False

            pdf_href = await pdf_link.get_attribute("href")
            if not pdf_href:
                logger.warning("PDF link has no href")
                return False

            actual_pdf_url = (cfg.base_url + pdf_href) if pdf_href.startswith("/") else pdf_href
            logger.info(f"Found PDF URL: {actual_pdf_url}")

            import os
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            try:
                async with page.expect_download(timeout=30000) as download_info:
                    await pdf_link.click()
                download = await download_info.value
                await download.save_as(save_path)
                size = os.path.getsize(save_path) if os.path.exists(save_path) else 0
                if size > 100:
                    logger.info(f"PDF downloaded: {save_path} ({size} bytes)")
                    return True
                logger.warning(f"Downloaded file too small: {size} bytes")
            except Exception as e:
                logger.warning(f"Download via click failed: {e}")

                cookies = await context.cookies()
                cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                try:
                    import aiohttp
                    headers = {"Cookie": cookie_header, "User-Agent": cfg.user_agent}
                    async with aiohttp.ClientSession() as session:
                        async with session.get(actual_pdf_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status == 200:
                                content = await resp.read()
                                if content and len(content) > 100:
                                    with open(save_path, "wb") as f:
                                        f.write(content)
                                    logger.info(f"PDF downloaded via aiohttp: {save_path} ({len(content)} bytes)")
                                    return True
                except Exception as e2:
                    logger.warning(f"aiohttp fallback also failed: {e2}")

            logger.warning(f"PDF download failed for {actual_pdf_url}")
            return False
        except Exception as e:
            logger.error(f"PDF download error: {e}")
            try:
                await self.close()
            except Exception:
                pass
            return False
        finally:
            await page.close()
            await context.close()

    async def get_facility_detail(self, facility_url: str) -> dict:
        """Navigate to a facility detail page and extract additional data."""
        cfg = self.config
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto(facility_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            detail = {}
            info_items = await page.query_selector_all(cfg.facility_detail_item_selector)
            for item in info_items:
                label_el = await item.query_selector(cfg.info_label_selector)
                value_el = await item.query_selector(cfg.info_value_selector)
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


# Backward compatibility alias
EMDScraper = InspectionScraper
