"""Fetch images for equipment catalog entries.

Run: /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/fetch_equipment_images.py
"""

import asyncio
import aiohttp
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from src.core.database import get_db_context
from src.models.equipment_catalog import EquipmentCatalog

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

UPLOAD_DIR = Path("/srv/quantumpools/app/uploads/equipment")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

DELAY = 2.5


async def fetch_image_url_duckduckgo(session: aiohttp.ClientSession, query: str) -> str | None:
    try:
        async with session.get(f"https://duckduckgo.com/?q={quote_plus(query)}", headers=HEADERS) as resp:
            text = await resp.text()
            vqd_match = re.search(r'vqd=["\']([^"\']+)', text)
            if not vqd_match:
                return None
            vqd = vqd_match.group(1)

        img_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={quote_plus(query)}&vqd={vqd}&f=,,,,,&p=1"
        async with session.get(img_url, headers=HEADERS) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            for r in data.get("results", [])[:5]:
                img = r.get("image", "")
                if img and not img.endswith(".svg") and "logo" not in img.lower():
                    return img
    except Exception:
        pass
    return None


async def download_image(session: aiohttp.ClientSession, url: str, entry_id: str) -> str | None:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            content_type = resp.headers.get("Content-Type", "")
            if "image" not in content_type and not url.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return None
            data = await resp.read()
            if len(data) < 1000:
                return None
            ext = "png" if "png" in content_type else "webp" if "webp" in content_type else "jpg"
            filename = f"{entry_id}.{ext}"
            (UPLOAD_DIR / filename).write_bytes(data)
            return f"/uploads/equipment/{filename}"
    except Exception:
        pass
    return None


async def main():
    async with get_db_context() as db:
        result = await db.execute(
            select(EquipmentCatalog).where(
                EquipmentCatalog.is_active == True,
                EquipmentCatalog.image_url.is_(None),
            ).order_by(EquipmentCatalog.manufacturer, EquipmentCatalog.canonical_name)
        )
        entries = result.scalars().all()
        log.info(f"Found {len(entries)} equipment without images")

        fetched = 0
        failed = 0

        async with aiohttp.ClientSession() as session:
            for i, entry in enumerate(entries):
                query = f"{entry.manufacturer or ''} {entry.canonical_name} pool equipment".strip()
                image_url = await fetch_image_url_duckduckgo(session, query)
                await asyncio.sleep(DELAY)

                if image_url:
                    local_path = await download_image(session, image_url, entry.id)
                    if local_path:
                        entry.image_url = local_path
                        fetched += 1
                        log.info(f"  [{i+1}/{len(entries)}] ✓ {entry.canonical_name}")
                    else:
                        failed += 1
                        log.info(f"  [{i+1}/{len(entries)}] ✗ {entry.canonical_name} (download failed)")
                else:
                    failed += 1
                    log.info(f"  [{i+1}/{len(entries)}] ✗ {entry.canonical_name} (no image)")

                if (i + 1) % 10 == 0:
                    await db.commit()

                await asyncio.sleep(DELAY)

        await db.commit()
        log.info(f"\nDone: {fetched} images, {failed} failed, {len(entries)} total")


if __name__ == "__main__":
    asyncio.run(main())
