"""Fetch images for parts catalog entries.

Uses multiple strategies:
1. Manufacturer CDN patterns (Pentair, Hayward, etc.)
2. Web search via DuckDuckGo images
3. Direct product page scraping

Run: /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/fetch_part_images.py
"""

import asyncio
import aiohttp
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update
from src.core.database import get_db_context
from src.models.parts_catalog import PartsCatalog

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

UPLOAD_DIR = Path("/srv/quantumpools/app/uploads/parts")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Rate limiting
DELAY = 1.5  # seconds between requests


async def fetch_image_url_duckduckgo(session: aiohttp.ClientSession, query: str) -> str | None:
    """Search DuckDuckGo images for a product image URL."""
    try:
        # DuckDuckGo image search via their API
        url = f"https://duckduckgo.com/?q={quote_plus(query)}&iax=images&ia=images"

        # Use the vqd token approach
        async with session.get(f"https://duckduckgo.com/?q={quote_plus(query)}", headers=HEADERS) as resp:
            text = await resp.text()
            vqd_match = re.search(r'vqd=["\']([^"\']+)', text)
            if not vqd_match:
                return None
            vqd = vqd_match.group(1)

        # Fetch image results
        img_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={quote_plus(query)}&vqd={vqd}&f=,,,,,&p=1"
        async with session.get(img_url, headers=HEADERS) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            results = data.get("results", [])

            # Filter for product images (avoid tiny icons, prefer larger images)
            for r in results[:5]:
                img = r.get("image", "")
                if img and not img.endswith(".svg") and "logo" not in img.lower():
                    return img
    except Exception as e:
        log.debug(f"DDG search failed for '{query}': {e}")
    return None


async def download_image(session: aiohttp.ClientSession, url: str, part_id: str) -> str | None:
    """Download image and save locally. Returns the relative path."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None

            content_type = resp.headers.get("Content-Type", "")
            if "image" not in content_type and not url.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return None

            data = await resp.read()
            if len(data) < 1000:  # Skip tiny images
                return None

            # Determine extension
            if "png" in content_type or url.endswith(".png"):
                ext = "png"
            elif "webp" in content_type or url.endswith(".webp"):
                ext = "webp"
            else:
                ext = "jpg"

            filename = f"{part_id}.{ext}"
            filepath = UPLOAD_DIR / filename
            filepath.write_bytes(data)

            return f"/uploads/parts/{filename}"
    except Exception as e:
        log.debug(f"Download failed for {url}: {e}")
    return None


async def fetch_images():
    async with get_db_context() as db:
        # Get parts without images
        result = await db.execute(
            select(PartsCatalog).where(
                PartsCatalog.is_chemical == False,
                PartsCatalog.image_url.is_(None),
            ).order_by(PartsCatalog.brand, PartsCatalog.name)
        )
        parts = result.scalars().all()

        log.info(f"Found {len(parts)} parts without images")

        fetched = 0
        failed = 0

        async with aiohttp.ClientSession() as session:
            for i, part in enumerate(parts):
                # Build search query — SKU is most specific
                queries = []
                if part.sku and not part.sku.startswith("AUTO-"):
                    queries.append(f"{part.brand} {part.sku} pool part")
                queries.append(f"{part.name} pool part")

                image_url = None
                for query in queries:
                    image_url = await fetch_image_url_duckduckgo(session, query)
                    if image_url:
                        break
                    await asyncio.sleep(DELAY)

                if image_url:
                    local_path = await download_image(session, image_url, part.id)
                    if local_path:
                        part.image_url = local_path
                        fetched += 1
                        log.info(f"  [{i+1}/{len(parts)}] ✓ {part.brand} {part.name}")
                    else:
                        failed += 1
                        log.info(f"  [{i+1}/{len(parts)}] ✗ {part.brand} {part.name} (download failed)")
                else:
                    failed += 1
                    log.info(f"  [{i+1}/{len(parts)}] ✗ {part.brand} {part.name} (no image found)")

                # Commit every 20 parts
                if (i + 1) % 20 == 0:
                    await db.commit()
                    log.info(f"  --- Committed batch ({fetched} fetched so far) ---")

                await asyncio.sleep(DELAY)

        await db.commit()
        log.info(f"\nDone: {fetched} images fetched, {failed} failed, {len(parts)} total")


if __name__ == "__main__":
    asyncio.run(fetch_images())
