"""Pool measurement service — Claude Vision analysis of tech photos for ground-truth dimensions."""

import base64
import json
import math
import uuid
import logging
from typing import Optional
from pathlib import Path

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import NotFoundError
from src.models.pool_measurement import PoolMeasurement
from src.models.property import Property
from src.models.body_of_water import BodyOfWater

logger = logging.getLogger(__name__)

MEASUREMENT_PROMPT = """You are analyzing photos of a swimming pool to determine its precise dimensions and volume.

PHOTOS PROVIDED:
- Overview photo(s): Show the full pool. A scale reference should be visible (see below).
- Depth marker photo(s): Show depth markers IN CONTEXT — the marker should be readable, but the surrounding pool perimeter, coping, and deck should also be visible so you can determine WHERE along the pool each marker is located.

SCALE REFERENCE: {scale_reference}

DEPTH MARKER TILES AS SCALE REFERENCE:
Most commercial pools have standardized depth marker tiles set into the coping or pool edge.
These tiles are almost always 6 inches × 6 inches (some are 6" × 12").
If you can see ANY depth marker tile in the photo, use it as your primary scale reference —
it is more reliable than a placed object because:
- It is a known, standardized size
- It is embedded in the pool structure (no parallax from placement)
- Multiple tiles at different positions give you multiple scale calibration points
Count tile widths along the pool edge to measure length and width.
If you see both tiles and another scale reference, cross-check them.

OTHER SCALE REFERENCES (if no tiles visible):
- Yardstick/meter stick: 36 inches (3 feet)
- Pool pole: typically 8 feet or 16 feet
- Standard shoe: approximately 12 inches
- Concrete expansion joint spacing: typically 10 feet
- Standard coping stones: typically 12 inches wide

INSTRUCTIONS:
1. Look for depth marker tiles first — they are the best scale reference
2. If tiles aren't visible, find the designated scale reference object
3. Use the scale to measure the pool's length and width in feet
4. Read ALL depth markers visible in the photos (e.g., "3 FT", "5 FT", "8 FT")
5. Note WHERE each marker is along the pool perimeter — this tells you the slope profile:
   - Which end is shallow vs deep
   - Where the transition/break point is
   - Whether it's a constant slope, hopper bottom, or multi-depth layout
6. Determine the pool shape
7. Calculate volume using the depth profile and these formulas:

VOLUME FORMULAS (cubic feet → gallons: multiply by 7.48):
- Rectangle: length × width × avg_depth × 7.48
- Oval: π × (length/2) × (width/2) × avg_depth × 7.48
- Round: π × radius² × avg_depth × 7.48
- Kidney/freeform: length × width × 0.45 × avg_depth × 7.48
- L-shape: calculate as two rectangles and sum

AVERAGE DEPTH — use the slope profile from marker positions:
- Constant slope (shallow → deep): (shallow + deep) / 2
- Hopper bottom (shallow shelf, steep drop to deep): (shallow × 0.4) + (deep × 0.6)
- Multi-depth (e.g., wading area + swim area + diving well): calculate each section separately by estimated area proportion

Return ONLY a JSON object:
{{
  "scale_reference_found": true/false,
  "scale_reference_type": "depth_marker_tile" | "yardstick" | "pool_pole" | "shoe" | "expansion_joint" | "other",
  "scale_reference_pixels": number (length of reference object in pixels, if found),
  "tiles_detected": number (count of depth marker tiles visible, 0 if none),
  "pool_length_ft": number,
  "pool_width_ft": number,
  "pool_shape": "rectangle" | "oval" | "kidney" | "L-shape" | "freeform" | "round",
  "depth_markers": [{{"value": "3 FT", "location": "north end, shallow"}}, ...],
  "depth_profile": "constant_slope" | "hopper" | "multi_depth" | "flat",
  "depth_shallow_ft": number,
  "depth_deep_ft": number,
  "depth_avg_ft": number (calculated using the appropriate method for the depth profile),
  "calculated_sqft": number,
  "calculated_gallons": number,
  "confidence": number 0.0-1.0,
  "has_spa": true/false,
  "notes": "any observations about the pool, slope profile, measurement quality, or concerns"
}}

Return ONLY the JSON object, no other text."""

SCALE_REFERENCE_LABELS = {
    "depth_marker_tile": "Depth marker tiles are visible at the pool edge (standard 6×6 inch tiles). Use them as the primary scale reference.",
    "pool_tile": "Depth marker tiles are visible at the pool edge (standard 6×6 inch tiles). Use them as the primary scale reference.",
    "yardstick": "The photographer placed a yardstick (36 inches / 3 feet) near the pool for scale.",
    "pool_pole_8ft": "The photographer placed an 8-foot pool pole near the pool for scale.",
    "pool_pole_16ft": "The photographer placed a 16-foot pool pole near the pool for scale.",
    "shoe": "The photographer placed a shoe (~12 inches) near the pool for scale.",
    "other": "The photographer placed an object of unknown size near the pool. Look for depth marker tiles or other known-size features to calibrate.",
}

# Volume calculation formulas (server-side validation)
VOLUME_FORMULAS = {
    "rectangle": lambda l, w, d: l * w * d * 7.48,
    "oval": lambda l, w, d: math.pi * (l / 2) * (w / 2) * d * 7.48,
    "round": lambda l, w, d: math.pi * (l / 2) ** 2 * d * 7.48,
    "kidney": lambda l, w, d: l * w * 0.45 * d * 7.48,
    "freeform": lambda l, w, d: l * w * 0.45 * d * 7.48,
    "L-shape": lambda l, w, d: l * w * 0.75 * d * 7.48,
}


class PoolMeasurementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if not self._client:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def upload_photos(
        self, org_id: str, property_id: str, photo_paths: list[dict], scale_reference: str,
        user_id: Optional[str] = None, body_of_water_id: Optional[str] = None,
    ) -> PoolMeasurement:
        prop = await self._get_property(org_id, property_id)
        if not prop:
            raise NotFoundError(f"Property {property_id} not found")

        # If no BOW specified, use primary
        if not body_of_water_id:
            bow_result = await self.db.execute(
                select(BodyOfWater).where(
                    BodyOfWater.property_id == property_id,
                    BodyOfWater.organization_id == org_id,
                    BodyOfWater.is_primary == True,
                )
            )
            primary_bow = bow_result.scalar_one_or_none()
            if primary_bow:
                body_of_water_id = primary_bow.id

        measurement = PoolMeasurement(
            id=str(uuid.uuid4()),
            property_id=property_id,
            organization_id=org_id,
            body_of_water_id=body_of_water_id,
            measured_by=user_id,
            scale_reference=scale_reference,
            photo_paths=photo_paths,
            status="pending",
        )
        self.db.add(measurement)
        await self.db.flush()
        await self.db.refresh(measurement)
        return measurement

    async def analyze(self, org_id: str, measurement_id: str) -> PoolMeasurement:
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        measurement = await self._get_measurement(org_id, measurement_id)
        if not measurement:
            raise NotFoundError(f"Measurement {measurement_id} not found")

        measurement.status = "analyzing"
        await self.db.flush()

        try:
            image_contents = self._load_photos(measurement.photo_paths or [])
            if not image_contents:
                raise ValueError("No valid photos found")

            scale_ref = measurement.scale_reference or "other"
            scale_desc = SCALE_REFERENCE_LABELS.get(scale_ref, SCALE_REFERENCE_LABELS["other"])
            prompt = MEASUREMENT_PROMPT.format(scale_reference=scale_desc)

            result = await self._call_claude(image_contents, prompt)

            measurement.length_ft = result.get("pool_length_ft")
            measurement.width_ft = result.get("pool_width_ft")
            measurement.depth_shallow_ft = result.get("depth_shallow_ft")
            measurement.depth_deep_ft = result.get("depth_deep_ft")
            measurement.depth_avg_ft = result.get("depth_avg_ft")
            measurement.pool_shape = result.get("pool_shape")
            measurement.confidence = result.get("confidence", 0)
            measurement.raw_analysis = result

            # Server-side volume calculation for validation
            if measurement.length_ft and measurement.width_ft and measurement.depth_avg_ft:
                shape = measurement.pool_shape or "rectangle"
                formula = VOLUME_FORMULAS.get(shape, VOLUME_FORMULAS["rectangle"])
                measurement.calculated_sqft = round(measurement.length_ft * measurement.width_ft, 1)
                if shape in ("kidney", "freeform"):
                    measurement.calculated_sqft = round(measurement.calculated_sqft * 0.85, 1)
                elif shape == "oval":
                    measurement.calculated_sqft = round(
                        math.pi * (measurement.length_ft / 2) * (measurement.width_ft / 2), 1
                    )
                elif shape == "round":
                    measurement.calculated_sqft = round(
                        math.pi * (measurement.length_ft / 2) ** 2, 1
                    )
                measurement.calculated_gallons = round(
                    formula(measurement.length_ft, measurement.width_ft, measurement.depth_avg_ft)
                )

            measurement.status = "completed"
            measurement.error_message = None

        except Exception as e:
            logger.error(f"Measurement analysis failed for {measurement_id}: {e}")
            measurement.status = "failed"
            measurement.error_message = str(e)

        await self.db.flush()
        await self.db.refresh(measurement)
        return measurement

    async def apply_to_property(self, org_id: str, measurement_id: str) -> tuple[PoolMeasurement, Property]:
        measurement = await self._get_measurement(org_id, measurement_id)
        if not measurement:
            raise NotFoundError(f"Measurement {measurement_id} not found")
        if measurement.status != "completed":
            raise ValueError("Can only apply completed measurements")

        prop = await self._get_property(org_id, measurement.property_id)
        if not prop:
            raise NotFoundError(f"Property {measurement.property_id} not found")

        # Write dimensions to BOW if available, also keep property in sync
        bow = None
        if measurement.body_of_water_id:
            bow_result = await self.db.execute(
                select(BodyOfWater).where(
                    BodyOfWater.id == measurement.body_of_water_id,
                    BodyOfWater.organization_id == org_id,
                )
            )
            bow = bow_result.scalar_one_or_none()

        targets = [prop]
        if bow:
            targets.append(bow)

        for target in targets:
            if measurement.length_ft:
                target.pool_length_ft = measurement.length_ft
            if measurement.width_ft:
                target.pool_width_ft = measurement.width_ft
            if measurement.depth_shallow_ft:
                target.pool_depth_shallow = measurement.depth_shallow_ft
            if measurement.depth_deep_ft:
                target.pool_depth_deep = measurement.depth_deep_ft
            if measurement.depth_avg_ft:
                target.pool_depth_avg = measurement.depth_avg_ft
            if measurement.calculated_sqft:
                target.pool_sqft = measurement.calculated_sqft
            if measurement.calculated_gallons:
                target.pool_gallons = measurement.calculated_gallons
            if measurement.pool_shape:
                target.pool_shape = measurement.pool_shape
            target.pool_volume_method = "measured"

        measurement.applied_to_property = True
        await self.db.flush()
        await self.db.refresh(prop)
        await self.db.refresh(measurement)
        return measurement, prop

    async def list_for_property(self, org_id: str, property_id: str) -> list[PoolMeasurement]:
        result = await self.db.execute(
            select(PoolMeasurement)
            .where(
                PoolMeasurement.property_id == property_id,
                PoolMeasurement.organization_id == org_id,
            )
            .order_by(PoolMeasurement.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_measurement(self, org_id: str, measurement_id: str) -> Optional[PoolMeasurement]:
        return await self._get_measurement(org_id, measurement_id)

    # --- Internal helpers ---

    async def _get_property(self, org_id: str, property_id: str) -> Optional[Property]:
        result = await self.db.execute(
            select(Property).where(Property.id == property_id, Property.organization_id == org_id)
        )
        return result.scalar_one_or_none()

    async def _get_measurement(self, org_id: str, measurement_id: str) -> Optional[PoolMeasurement]:
        result = await self.db.execute(
            select(PoolMeasurement).where(
                PoolMeasurement.id == measurement_id,
                PoolMeasurement.organization_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    def _load_photos(self, photo_paths: list[dict]) -> list[dict]:
        """Load photo files from disk and return as base64-encoded content blocks."""
        contents = []
        upload_dir = Path(settings.upload_dir)
        for photo in photo_paths:
            filepath = upload_dir / photo["path"]
            if not filepath.exists():
                logger.warning(f"Photo not found: {filepath}")
                continue
            data = filepath.read_bytes()
            ext = filepath.suffix.lower()
            media_type = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".heic": "image/jpeg", ".heif": "image/jpeg",
            }.get(ext, "image/jpeg")
            contents.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()},
            })
        return contents

    async def _call_claude(self, image_contents: list[dict], text: str) -> dict:
        """Send multiple images + text to Claude Vision, parse JSON response."""
        content = image_contents + [{"type": "text", "text": text}]
        message = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )
        response = message.content[0].text.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response[:-3].strip()
        return json.loads(response)
