"""Satellite analysis service — Google Maps Static API + Claude Vision for pool/vegetation detection.

Two-pass approach:
  1. LOCATE: Wide zoom (18) image → Claude finds the pool's pixel position → convert to lat/lng
  2. ANALYZE: Zoomed-in (20) image centered on the pool → Claude measures and analyzes
"""

import base64
import json
import math
import uuid
import logging
from typing import Optional

import aiohttp
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import NotFoundError
from src.models.satellite_analysis import SatelliteAnalysis
from src.models.property import Property

logger = logging.getLogger(__name__)

# --- Prompts ---

LOCATE_PROMPT = """This satellite image is centered on a property address. The property has a swimming pool somewhere in or near this image.

Find the pool and return its pixel coordinates in the image (origin is top-left).

The image is {width}x{height} pixels. Each pixel is approximately {ft_per_px:.1f} feet.

Return ONLY a JSON object:
{{
  "pool_found": true/false,
  "pool_x": number (center X pixel of the pool),
  "pool_y": number (center Y pixel of the pool),
  "notes": "brief description of where you found it"
}}

Look carefully — the pool may be:
- Behind buildings (apartment complex pools are often in interior courtyards)
- Under partial tree canopy
- A non-standard color (green, dark, covered)
- Small relative to the property

Return ONLY the JSON object, no other text."""

ANALYSIS_PROMPT = """Analyze this satellite image centered on a swimming pool.

SCALE: This image is {width}x{height} pixels. Each pixel ≈ {ft_per_px:.2f} feet ({sqft_per_px:.3f} sqft/pixel). The full image spans {img_width_ft:.0f} × {img_height_ft:.0f} feet. A car is about {car_px:.0f} pixels long.

MEASURE the pool precisely:
1. Estimate the pool's width and height in PIXELS
2. Calculate sqft = width_px × height_px × {sqft_per_px:.3f}
3. For non-rectangular shapes (kidney, oval, freeform), multiply by 0.70-0.75

Return ONLY a JSON object:
{{
  "pool_detected": true/false,
  "pool_pixel_width": number (pool width in pixels),
  "pool_pixel_height": number (pool height in pixels),
  "estimated_pool_sqft": number (calculated as described above),
  "pool_shape": "rectangle" | "kidney" | "L-shape" | "freeform" | "oval" | "round",
  "pool_confidence": number 0.0-1.0,
  "vegetation_pct": number 0-100,
  "canopy_overhang_pct": number 0-100 (tree canopy near/over the pool),
  "hardscape_pct": number 0-100,
  "shadow_pct": number 0-100,
  "has_spa": true/false,
  "has_pool_cover": true/false,
  "deck_material": "concrete" | "pavers" | "wood" | "stone" | null,
  "notes": "brief observation relevant to pool service"
}}

This property HAS a pool — it should be visible near the center of this image.
Return ONLY the JSON object, no other text."""


class SatelliteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if not self._client:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def get_analysis(self, organization_id: str, property_id: str) -> Optional[SatelliteAnalysis]:
        result = await self.db.execute(
            select(SatelliteAnalysis).where(
                SatelliteAnalysis.property_id == property_id,
                SatelliteAnalysis.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def analyze_property(
        self, organization_id: str, property_id: str, force: bool = False
    ) -> SatelliteAnalysis:
        if not settings.google_maps_api_key:
            raise ValueError("Google Maps API key not configured")
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        result = await self.db.execute(
            select(Property).where(
                Property.id == property_id,
                Property.organization_id == organization_id,
            )
        )
        prop = result.scalar_one_or_none()
        if not prop:
            raise NotFoundError(f"Property {property_id} not found")

        if not prop.lat or not prop.lng:
            raise ValueError(f"Property {property_id} has no coordinates — geocode first")

        existing = await self.get_analysis(organization_id, property_id)
        if existing and not force:
            return existing

        width, height = 640, 640

        # --- Pass 1: LOCATE the pool (wide view ~500m across) ---
        locate_zoom = 17
        locate_url = self._build_image_url(prop.lat, prop.lng, locate_zoom, width, height)
        locate_bytes = await self._fetch_image(locate_url)

        if not locate_bytes:
            return await self._save_error(
                organization_id, property_id, existing,
                "Failed to fetch wide satellite image",
                locate_url, locate_zoom, width, height,
            )

        pool_lat, pool_lng = prop.lat, prop.lng  # default to property center
        try:
            location = await self._locate_pool(locate_bytes, prop.lat, prop.lng, locate_zoom, width, height)
            if location:
                pool_lat, pool_lng = location
                logger.info(f"Pool located at {pool_lat:.6f},{pool_lng:.6f} (offset from address {prop.lat:.6f},{prop.lng:.6f})")
        except Exception as e:
            logger.warning(f"Pool location failed for {property_id}, using address center: {e}")

        # --- Pass 2: ANALYZE — try zoom 21 (best detail), fall back to 20 (wider) ---
        results = None
        analyze_url = None
        analyze_zoom = None

        for zoom_level in [21, 20]:
            analyze_zoom = zoom_level
            analyze_url = self._build_image_url(pool_lat, pool_lng, zoom_level, width, height)
            analyze_bytes = await self._fetch_image(analyze_url)
            if not analyze_bytes:
                continue
            try:
                results = await self._analyze_pool(
                    analyze_bytes, prop.address, pool_lat, zoom_level, width, height,
                )
                if results["pool_detected"]:
                    break
                logger.info(f"Pool not found at zoom {zoom_level} for {prop.address}, trying wider")
            except Exception as e:
                logger.warning(f"Analysis at zoom {zoom_level} failed for {property_id}: {e}")

        if not results:
            return await self._save_error(
                organization_id, property_id, existing,
                "Pool not detected at any zoom level",
                analyze_url or "", analyze_zoom or 21, width, height,
            )

        # Update property pool_sqft if detected and not already set
        if results["pool_detected"] and results["estimated_pool_sqft"] and not prop.pool_sqft:
            prop.pool_sqft = results["estimated_pool_sqft"]

        return await self._save_analysis(
            organization_id, property_id, existing,
            pool_detected=results["pool_detected"],
            estimated_pool_sqft=results["estimated_pool_sqft"],
            pool_contour_points=None,
            pool_confidence=results["pool_confidence"],
            vegetation_pct=results["vegetation_pct"],
            canopy_overhang_pct=results["canopy_overhang_pct"],
            hardscape_pct=results["hardscape_pct"],
            shadow_pct=results["shadow_pct"],
            image_url=analyze_url, image_zoom=analyze_zoom,
            image_width=width, image_height=height,
            raw_results=results,
        )

    async def bulk_analyze(
        self, organization_id: str, property_ids: Optional[list[str]] = None, force: bool = False
    ) -> dict:
        if property_ids:
            result = await self.db.execute(
                select(Property).where(
                    Property.organization_id == organization_id,
                    Property.id.in_(property_ids),
                    Property.is_active == True,
                )
            )
        else:
            result = await self.db.execute(
                select(Property).where(
                    Property.organization_id == organization_id,
                    Property.is_active == True,
                    Property.lat.isnot(None),
                    Property.lng.isnot(None),
                )
            )
        properties = result.scalars().all()

        analyzed, skipped, failed = [], 0, 0
        for prop in properties:
            if not prop.lat or not prop.lng:
                skipped += 1
                continue
            try:
                analysis = await self.analyze_property(organization_id, prop.id, force=force)
                if analysis.error_message:
                    failed += 1
                else:
                    analyzed.append(analysis)
            except Exception as e:
                logger.error(f"Bulk analysis failed for {prop.id}: {e}")
                failed += 1

        await self.db.flush()
        return {
            "total": len(properties),
            "analyzed": len(analyzed),
            "skipped": skipped,
            "failed": failed,
            "results": analyzed,
        }

    # --- Image helpers ---

    def _build_image_url(self, lat: float, lng: float, zoom: int, width: int, height: int) -> str:
        return (
            f"https://maps.googleapis.com/maps/api/staticmap"
            f"?center={lat},{lng}&zoom={zoom}&size={width}x{height}"
            f"&maptype=satellite&key={settings.google_maps_api_key}"
        )

    async def _fetch_image(self, url: str) -> Optional[bytes]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        content_type = resp.headers.get("Content-Type", "")
                        if "image" in content_type:
                            return data
                        logger.warning(f"Static Maps returned non-image: {content_type}")
                    else:
                        logger.warning(f"Static Maps returned {resp.status}")
        except Exception as e:
            logger.error(f"Failed to fetch satellite image: {e}")
        return None

    # --- Scale math ---

    def _scale_info(self, lat: float, zoom: int, width: int, height: int) -> dict:
        meters_per_px = 0.149 * (2 ** (20 - zoom)) / math.cos(math.radians(lat))
        ft_per_px = meters_per_px * 3.28084
        return {
            "meters_per_px": meters_per_px,
            "ft_per_px": ft_per_px,
            "sqft_per_px": ft_per_px * ft_per_px,
            "img_width_ft": width * ft_per_px,
            "img_height_ft": height * ft_per_px,
            "car_px": 15.0 / ft_per_px,
        }

    def _pixel_to_latlng(
        self, px_x: int, px_y: int,
        center_lat: float, center_lng: float,
        zoom: int, width: int, height: int,
    ) -> tuple[float, float]:
        """Convert pixel coordinates in the image to lat/lng."""
        meters_per_px = 0.149 * (2 ** (20 - zoom)) / math.cos(math.radians(center_lat))

        # Pixel offset from center
        dx = px_x - width / 2
        dy = px_y - height / 2

        # Convert to meters, then to degrees
        meters_east = dx * meters_per_px
        meters_south = dy * meters_per_px

        lat = center_lat - (meters_south / 111320)
        lng = center_lng + (meters_east / (111320 * math.cos(math.radians(center_lat))))

        return lat, lng

    # --- Claude calls ---

    async def _call_claude(self, image_bytes: bytes, text: str) -> str:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        message = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                    },
                    {"type": "text", "text": text},
                ],
            }],
        )
        response = message.content[0].text.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response[:-3].strip()
        return response

    async def _locate_pool(
        self, image_bytes: bytes,
        center_lat: float, center_lng: float,
        zoom: int, width: int, height: int,
    ) -> Optional[tuple[float, float]]:
        """Pass 1: Find the pool in a wide-angle image, return its lat/lng."""
        scale = self._scale_info(center_lat, zoom, width, height)
        prompt = LOCATE_PROMPT.format(
            width=width, height=height, ft_per_px=scale["ft_per_px"],
        )

        response = await self._call_claude(image_bytes, prompt)
        result = json.loads(response)

        if not result.get("pool_found"):
            return None

        px_x = result.get("pool_x", width // 2)
        px_y = result.get("pool_y", height // 2)

        # Only use if meaningfully different from center (>30px offset)
        if abs(px_x - width // 2) < 30 and abs(px_y - height // 2) < 30:
            return None  # pool is near center anyway, no offset needed

        return self._pixel_to_latlng(px_x, px_y, center_lat, center_lng, zoom, width, height)

    async def _analyze_pool(
        self, image_bytes: bytes, address: str,
        lat: float, zoom: int, width: int, height: int,
    ) -> dict:
        """Pass 2: Detailed analysis of zoomed-in pool image."""
        scale = self._scale_info(lat, zoom, width, height)
        prompt = ANALYSIS_PROMPT.format(
            width=width, height=height,
            ft_per_px=scale["ft_per_px"],
            sqft_per_px=scale["sqft_per_px"],
            img_width_ft=scale["img_width_ft"],
            img_height_ft=scale["img_height_ft"],
            car_px=scale["car_px"],
        )

        response = await self._call_claude(
            image_bytes,
            f"Property address: {address}\n\n{prompt}",
        )
        result = json.loads(response)

        return {
            "pool_detected": bool(result.get("pool_detected", False)),
            "estimated_pool_sqft": result.get("estimated_pool_sqft"),
            "pool_shape": result.get("pool_shape"),
            "pool_contour_points": None,
            "pool_confidence": float(result.get("pool_confidence", 0)),
            "vegetation_pct": float(result.get("vegetation_pct", 0)),
            "canopy_overhang_pct": float(result.get("canopy_overhang_pct", 0)),
            "hardscape_pct": float(result.get("hardscape_pct", 0)),
            "shadow_pct": float(result.get("shadow_pct", 0)),
            "has_spa": result.get("has_spa", False),
            "has_pool_cover": result.get("has_pool_cover", False),
            "deck_material": result.get("deck_material"),
            "notes": result.get("notes"),
        }

    # --- Persistence ---

    async def _save_error(
        self, organization_id: str, property_id: str,
        existing: Optional[SatelliteAnalysis],
        error_message: str, image_url: str, zoom: int, width: int, height: int,
    ) -> SatelliteAnalysis:
        return await self._save_analysis(
            organization_id, property_id, existing,
            error_message=error_message,
            image_url=image_url, image_zoom=zoom,
            image_width=width, image_height=height,
        )

    async def _save_analysis(
        self, organization_id: str, property_id: str,
        existing: Optional[SatelliteAnalysis], **kwargs
    ) -> SatelliteAnalysis:
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            existing.analysis_version = "3.0"
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        analysis = SatelliteAnalysis(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            property_id=property_id,
            **kwargs,
        )
        self.db.add(analysis)
        await self.db.flush()
        await self.db.refresh(analysis)
        return analysis
