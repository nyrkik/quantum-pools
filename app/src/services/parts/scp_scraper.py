"""SCP Catalog Scraper — Playwright-based scraper for pool360.com product catalog.

NOTE: pool360.com requires authentication for catalog browsing.
The public catalog is not accessible without login credentials.
This scraper is a placeholder for future implementation when SCP credentials
are available. In the meantime, use seed_catalog() to populate common parts.

For now, the parts_catalog table is populated via the seed script at
/srv/quantumpools/app/src/services/parts/seed_catalog.py
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.parts_catalog import PartsCatalog

logger = logging.getLogger(__name__)

# Categories to scrape when auth is available
SCP_CATEGORIES = [
    "Pumps", "Filters", "Heaters", "Cleaners", "Chemicals",
    "Valves", "Motors", "Automation", "Lighting", "Accessories",
]

DEFAULT_RATE_LIMIT = 2  # seconds between requests


class SCPScraper:
    """Playwright-based scraper for SCP/Pool360 catalog.

    Currently a stub — pool360.com requires authentication.
    Use seed_catalog() for initial data population.
    """

    def __init__(self, rate_limit_seconds: int = DEFAULT_RATE_LIMIT, max_pages: int = 5):
        self.rate_limit_seconds = rate_limit_seconds
        self.max_pages = max_pages
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self):
        if self._browser and self._browser.is_connected():
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        logger.info("Playwright browser launched for SCP scraper")

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def scrape_catalog(self, db: AsyncSession) -> dict:
        """Scrape SCP catalog. Returns summary stats.

        Currently returns error since pool360.com requires auth.
        """
        return {
            "status": "not_available",
            "message": "pool360.com requires authentication. Use seed_catalog endpoint instead.",
            "categories": SCP_CATEGORIES,
        }

    async def _upsert_part(self, db: AsyncSession, part_data: dict) -> bool:
        """Upsert a single part into parts_catalog. Returns True if new."""
        import uuid
        result = await db.execute(
            select(PartsCatalog).where(
                PartsCatalog.vendor_provider == part_data["vendor_provider"],
                PartsCatalog.sku == part_data["sku"],
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key in ("name", "brand", "category", "subcategory", "description",
                        "image_url", "product_url", "specs", "compatible_with", "is_chemical"):
                if key in part_data:
                    setattr(existing, key, part_data[key])
            existing.last_scraped_at = datetime.now(timezone.utc)
            return False
        else:
            part = PartsCatalog(
                id=str(uuid.uuid4()),
                vendor_provider=part_data["vendor_provider"],
                sku=part_data["sku"],
                name=part_data["name"],
                brand=part_data.get("brand"),
                category=part_data.get("category"),
                subcategory=part_data.get("subcategory"),
                description=part_data.get("description"),
                image_url=part_data.get("image_url"),
                product_url=part_data.get("product_url"),
                specs=part_data.get("specs"),
                compatible_with=part_data.get("compatible_with"),
                is_chemical=part_data.get("is_chemical", False),
                last_scraped_at=datetime.now(timezone.utc),
            )
            db.add(part)
            return True
