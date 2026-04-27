#!/usr/bin/env python
"""Load a test-strip brand + per-pad color chart from a reference image.

Workflow:
  1. You provide a clean image of the brand's color chart (the printed
     reference scale, usually on the bottle). Pass `--image-path` (local) or
     `--image-url` (downloaded with urllib).
  2. Script asks Claude Haiku Vision to extract the structured chart:
     pad order, chemistry fields, value rows with hex colors.
  3. Inserts/updates rows in `test_strip_brands` + `test_strip_pads`.

Usage:
    python scripts/load_test_strip_brand.py \
      --name "AquaChek 7-way Pool" --manufacturer "AquaChek" \
      --image-path /tmp/aquachek-7way.jpg [--dry-run]

    python scripts/load_test_strip_brand.py \
      --name "Industrial Test Systems WaterWorks" --manufacturer "Industrial Test Systems" \
      --image-url https://example.com/it-systems-chart.jpg

Idempotency: if a brand with the same `name` already exists, its pads are
deleted and re-created from the new chart parse. Existing brand_id is preserved
so any FKs (none today) wouldn't break.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
import uuid
from pathlib import Path

import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.core.database import get_db_context
from src.models.test_strip_brand import TestStripBrand, TestStripPad

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("load_test_strip_brand")


PARSE_PROMPT = """You are extracting the printed color reference chart from a pool/spa test strip bottle photograph.

Identify each colored row/column as one PAD. For each pad, return:
- pad_index: 0-based, in order from the dipped end (closer to fingers when reading) to the handle end. If the chart prints them differently, infer the actual strip order.
- chemistry_field: one of these EXACT strings only:
    "ph", "free_chlorine", "total_chlorine", "alkalinity", "calcium_hardness",
    "cyanuric_acid", "salt", "phosphates", "tds", "total_hardness", "bromine"
- unit: e.g. "ppm" for chlorine/alkalinity, "" (empty) for pH
- color_scale: ordered list (lowest value first) of {"value": <number>, "hex": "#RRGGBB"}.
  Sample colors AT THE CENTER of each printed swatch on the chart.

Notes:
- A 7-way strip typically has 7 pads. Number them 0..6.
- "Total hardness" sometimes appears alongside calcium hardness — keep them as separate pads if so.
- If a pad reads bromine instead of chlorine, label it bromine.
- Skip any decorative/branding swatches that don't represent measurements.

Return ONLY this JSON, no markdown:
{
  "brand_name_seen": "string from the bottle/chart",
  "manufacturer_seen": "string or null",
  "num_pads": <integer>,
  "pads": [
    {
      "pad_index": 0,
      "chemistry_field": "...",
      "unit": "...",
      "color_scale": [{"value": <num>, "hex": "#RRGGBB"}, ...]
    }
  ],
  "extraction_confidence": 0.0-1.0,
  "extraction_notes": "anything unusual about the chart"
}
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def _load_image(image_path: str | None, image_url: str | None) -> tuple[bytes, str]:
    if image_path:
        data = Path(image_path).read_bytes()
        media_type = _guess_media_type(image_path)
        return data, media_type
    if image_url:
        with urllib.request.urlopen(image_url, timeout=30) as resp:
            data = resp.read()
            media_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            if not media_type.startswith("image/"):
                media_type = "image/jpeg"
            return data, media_type
    raise ValueError("must pass --image-path or --image-url")


def _guess_media_type(path: str) -> str:
    p = path.lower()
    if p.endswith(".png"):
        return "image/png"
    if p.endswith(".webp"):
        return "image/webp"
    if p.endswith(".heic"):
        return "image/heic"
    return "image/jpeg"


async def parse_chart(image_bytes: bytes, media_type: str) -> dict:
    client = anthropic.Anthropic()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    response = client.messages.create(
        model=await get_model("fast"),
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": PARSE_PROMPT},
                ],
            }
        ],
    )
    raw = response.content[0].text
    return json.loads(_strip_code_fence(raw))


async def upsert_brand(
    db: AsyncSession,
    name: str,
    manufacturer: str | None,
    aliases: list[str],
    source_url: str | None,
    parse: dict,
    dry_run: bool,
) -> str:
    """Insert or update brand + pads. Returns brand_id."""
    result = await db.execute(select(TestStripBrand).where(TestStripBrand.name == name))
    brand = result.scalar_one_or_none()

    if brand is None:
        brand = TestStripBrand(
            id=str(uuid.uuid4()),
            name=name,
            manufacturer=manufacturer,
            num_pads=parse.get("num_pads") or len(parse.get("pads") or []),
            aliases=aliases,
            source_url=source_url,
            notes=parse.get("extraction_notes") or None,
            is_active=True,
        )
        if not dry_run:
            db.add(brand)
            await db.flush()
        action = "INSERT"
    else:
        brand.manufacturer = manufacturer or brand.manufacturer
        brand.num_pads = parse.get("num_pads") or len(parse.get("pads") or []) or brand.num_pads
        brand.aliases = list(set(list(brand.aliases or []) + aliases))
        brand.source_url = source_url or brand.source_url
        brand.notes = parse.get("extraction_notes") or brand.notes
        brand.is_active = True
        action = "UPDATE"
        # Drop old pads — we're re-seeding from the parsed chart
        if not dry_run:
            await db.execute(
                TestStripPad.__table__.delete().where(TestStripPad.brand_id == brand.id)
            )

    logger.info(f"{action}: brand={brand.name} (id={brand.id}) num_pads={brand.num_pads}")

    pads_input = parse.get("pads") or []
    for p in pads_input:
        pad = TestStripPad(
            id=str(uuid.uuid4()),
            brand_id=brand.id,
            pad_index=int(p["pad_index"]),
            chemistry_field=p["chemistry_field"],
            unit=p.get("unit") or None,
            color_scale=p["color_scale"],
        )
        logger.info(
            f"  pad #{pad.pad_index}: {pad.chemistry_field} ({pad.unit or '—'}) "
            f"scale={[(s['value'], s['hex']) for s in pad.color_scale]}"
        )
        if not dry_run:
            db.add(pad)

    if not dry_run:
        await db.commit()
    return brand.id


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--manufacturer", default=None)
    parser.add_argument("--alias", action="append", default=[], help="Repeatable")
    parser.add_argument("--image-path", default=None)
    parser.add_argument("--image-url", default=None)
    parser.add_argument("--source-url", default=None,
                        help="Optional reference URL (e.g. manufacturer product page)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    image_bytes, media_type = _load_image(args.image_path, args.image_url)
    logger.info(f"Loaded image: {len(image_bytes)} bytes, {media_type}")

    parse = await parse_chart(image_bytes, media_type)
    logger.info(f"Vision extracted: {parse.get('num_pads')} pads, "
                f"confidence={parse.get('extraction_confidence')}, "
                f"brand_seen={parse.get('brand_name_seen')!r}")

    async with get_db_context() as db:
        brand_id = await upsert_brand(
            db,
            name=args.name,
            manufacturer=args.manufacturer,
            aliases=args.alias,
            source_url=args.source_url or args.image_url,
            parse=parse,
            dry_run=args.dry_run,
        )
        logger.info(f"Done. brand_id={brand_id} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
