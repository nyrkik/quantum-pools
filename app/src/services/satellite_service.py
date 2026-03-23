"""Satellite analysis service v5 — Per-WF analysis (pools only).

Each pool WF gets its own pin and analysis. Spas/fountains excluded.
SatelliteImages stay property-keyed (one set of overhead photos per yard).
"""

import base64
import json
import math
import re
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
from src.models.water_feature import WaterFeature

logger = logging.getLogger(__name__)

MEASURE_PROMPT = """Analyze this satellite image of a swimming pool. The pool is at the CENTER of these images.

Image 1 is zoomed in (detail view). Image 2 is a wider context view.

SCALE (Image 1): {width}x{height} pixels. Each pixel ≈ {ft_per_px_z21:.2f} feet ({sqft_per_px_z21:.3f} sqft/pixel). Full image spans {img_width_ft_z21:.0f} × {img_height_ft_z21:.0f} feet. A car ≈ {car_px_z21:.0f} pixels long.

SCALE (Image 2): Each pixel ≈ {ft_per_px_z20:.2f} feet ({sqft_per_px_z20:.3f} sqft/pixel). Full image spans {img_width_ft_z20:.0f} × {img_height_ft_z20:.0f} feet.

MEASURE the pool precisely using Image 1:
1. Estimate the pool's width and height in PIXELS
2. Calculate sqft = width_px × height_px × {sqft_per_px_z21:.3f}
3. For non-rectangular shapes (kidney, oval, freeform), multiply by 0.70-0.75

SANITY CHECK:
- Typical residential pool: 300-800 sqft
- Large commercial pool: 1000-3000 sqft
- Olympic pool: ~8000 sqft
- If your estimate exceeds 5000 sqft, re-examine — you may be measuring the deck or parking lot

Use Image 2 (wider view) to understand the property context, vegetation, and surroundings.

Return ONLY a JSON object:
{{
  "pool_detected": true/false,
  "pool_pixel_width": number (pool width in pixels, Image 1),
  "pool_pixel_height": number (pool height in pixels, Image 1),
  "estimated_pool_sqft": number (calculated as described above),
  "pool_shape": "rectangle" | "kidney" | "L-shape" | "freeform" | "oval" | "round",
  "pool_confidence": number 0.0-1.0,
  "vegetation_pct": number 0-100 (property-wide),
  "canopy_overhang_pct": number 0-100 (tree canopy near/over the pool),
  "hardscape_pct": number 0-100,
  "shadow_pct": number 0-100,
  "has_spa": true/false,
  "has_pool_cover": true/false,
  "deck_material": "concrete" | "pavers" | "wood" | "stone" | null,
  "notes": "brief observation relevant to pool service"
}}

This property HAS a pool — it should be visible at the center.
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

    async def _get_bow(self, organization_id: str, wf_id: str) -> WaterFeature:
        result = await self.db.execute(
            select(WaterFeature).where(
                WaterFeature.id == wf_id,
                WaterFeature.organization_id == organization_id,
            )
        )
        wf = result.scalar_one_or_none()
        if not wf:
            raise NotFoundError(f"Body of water {wf_id} not found")
        if wf.water_type != "pool":
            raise ValueError(f"Satellite analysis only applies to pools, not {wf.water_type}")
        return wf

    async def _get_property(self, organization_id: str, property_id: str) -> Property:
        result = await self.db.execute(
            select(Property).where(
                Property.id == property_id,
                Property.organization_id == organization_id,
            )
        )
        prop = result.scalar_one_or_none()
        if not prop:
            raise NotFoundError(f"Property {property_id} not found")
        return prop

    async def get_analysis(self, organization_id: str, wf_id: str) -> Optional[SatelliteAnalysis]:
        result = await self.db.execute(
            select(SatelliteAnalysis).where(
                SatelliteAnalysis.water_feature_id == wf_id,
                SatelliteAnalysis.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_pool_pin(
        self, organization_id: str, wf_id: str, pool_lat: float, pool_lng: float
    ) -> SatelliteAnalysis:
        wf = await self._get_bow(organization_id, wf_id)
        prop = await self._get_property(organization_id, wf.property_id)

        existing = await self.get_analysis(organization_id, wf_id)
        if existing:
            existing.pool_lat = pool_lat
            existing.pool_lng = pool_lng
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        analysis = SatelliteAnalysis(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            property_id=prop.id,
            water_feature_id=wf_id,
            pool_lat=pool_lat,
            pool_lng=pool_lng,
            analysis_version="5.0",
        )
        self.db.add(analysis)
        await self.db.flush()
        await self.db.refresh(analysis)
        return analysis

    async def get_pool_bows_with_coords(self, organization_id: str) -> list[dict]:
        """List all pool WFs with property coordinates, analysis status, and assigned tech."""
        from src.models.customer import Customer
        from src.models.route import Route, RouteStop
        from src.models.tech import Tech
        from sqlalchemy import func
        from sqlalchemy.orm import aliased

        SA = aliased(SatelliteAnalysis)

        # Scalar subqueries for primary tech (first alphabetically) per property
        tech_name_subq = (
            select(func.concat(Tech.first_name, ' ', Tech.last_name))
            .join(Route, Route.tech_id == Tech.id)
            .join(RouteStop, RouteStop.route_id == Route.id)
            .where(RouteStop.property_id == Property.id)
            .order_by(Tech.first_name)
            .limit(1)
            .correlate(Property)
            .scalar_subquery()
            .label("tech_name")
        )
        tech_color_subq = (
            select(Tech.color)
            .join(Route, Route.tech_id == Tech.id)
            .join(RouteStop, RouteStop.route_id == Route.id)
            .where(RouteStop.property_id == Property.id)
            .order_by(Tech.first_name)
            .limit(1)
            .correlate(Property)
            .scalar_subquery()
            .label("tech_color")
        )

        result = await self.db.execute(
            select(
                WaterFeature.id,
                WaterFeature.property_id,
                WaterFeature.name,
                WaterFeature.water_type,
                WaterFeature.pool_sqft,
                Property.address,
                Property.city,
                Customer.display_name_col.label("customer_name"),
                Customer.id.label("customer_id"),
                Customer.customer_type,
                Property.lat,
                Property.lng,
                SA.pool_lat,
                SA.pool_lng,
                SA.pool_detected,
                tech_name_subq,
                tech_color_subq,
            )
            .join(Property, WaterFeature.property_id == Property.id)
            .join(Customer, Property.customer_id == Customer.id)
            .outerjoin(SA, SA.water_feature_id == WaterFeature.id)
            .where(
                WaterFeature.organization_id == organization_id,
                WaterFeature.is_active == True,
                Customer.is_active == True,
                Property.is_active == True,
                Property.lat.isnot(None),
                Property.lng.isnot(None),
            )
        )
        rows = result.all()

        return [
            {
                "id": row.id,
                "property_id": row.property_id,
                "bow_name": row.name,
                "water_type": row.water_type,
                "address": row.address or "",
                "city": row.city or "",
                "customer_name": row.customer_name or "",
                "customer_id": row.customer_id,
                "customer_type": row.customer_type or "residential",
                "pool_sqft": row.pool_sqft,
                "lat": row.lat,
                "lng": row.lng,
                "pool_lat": row.pool_lat,
                "pool_lng": row.pool_lng,
                "has_analysis": bool(row.pool_detected),
                "tech_name": row.tech_name,
                "tech_color": row.tech_color,
            }
            for row in rows
        ]

    async def analyze_bow(
        self, organization_id: str, wf_id: str,
        force: bool = False,
        pool_lat: Optional[float] = None, pool_lng: Optional[float] = None,
    ) -> SatelliteAnalysis:
        if not settings.google_maps_api_key:
            raise ValueError("Google Maps API key not configured")
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        wf = await self._get_bow(organization_id, wf_id)
        prop = await self._get_property(organization_id, wf.property_id)

        if not prop.lat or not prop.lng:
            raise ValueError(f"Property {prop.id} has no coordinates — geocode first")

        existing = await self.get_analysis(organization_id, wf_id)
        if existing and not force:
            return existing

        # If pin coords provided in request, save them first
        if pool_lat is not None and pool_lng is not None:
            if existing:
                existing.pool_lat = pool_lat
                existing.pool_lng = pool_lng
            else:
                existing = SatelliteAnalysis(
                    id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    property_id=prop.id,
                    water_feature_id=wf_id,
                    pool_lat=pool_lat,
                    pool_lng=pool_lng,
                )
                self.db.add(existing)
                await self.db.flush()

        # Determine analysis center: pin > existing pin > property geocode
        center_lat = pool_lat or (existing.pool_lat if existing else None) or prop.lat
        center_lng = pool_lng or (existing.pool_lng if existing else None) or prop.lng

        width, height = 640, 640

        # Fetch two images: zoom 21 (detail) + zoom 20 (context)
        url_z21 = self._build_image_url(center_lat, center_lng, 21, width, height)
        url_z20 = self._build_image_url(center_lat, center_lng, 20, width, height)

        bytes_z21 = await self._fetch_image(url_z21)
        bytes_z20 = await self._fetch_image(url_z20)

        if not bytes_z21 and not bytes_z20:
            return await self._save_error(
                organization_id, prop.id, wf_id, existing,
                "Failed to fetch satellite images",
                url_z21, 21, width, height,
            )

        if not bytes_z21:
            bytes_z21 = bytes_z20
            url_z21 = url_z20

        try:
            results = await self._measure_pool(
                bytes_z21, bytes_z20, prop.address,
                center_lat, width, height,
            )
        except Exception as e:
            logger.error(f"Claude analysis failed for WF {wf_id}: {e}")
            return await self._save_error(
                organization_id, prop.id, wf_id, existing,
                f"Claude analysis failed: {e}",
                url_z21, 21, width, height,
            )

        if not results:
            return await self._save_error(
                organization_id, prop.id, wf_id, existing,
                "Pool not detected",
                url_z21, 21, width, height,
            )

        # Update pool_sqft on this WF only
        if results["pool_detected"] and results["estimated_pool_sqft"] and not wf.pool_sqft:
            wf.pool_sqft = results["estimated_pool_sqft"]

        return await self._save_analysis(
            organization_id, prop.id, wf_id, existing,
            pool_detected=results["pool_detected"],
            estimated_pool_sqft=results["estimated_pool_sqft"],
            pool_contour_points=None,
            pool_confidence=results["pool_confidence"],
            vegetation_pct=results["vegetation_pct"],
            canopy_overhang_pct=results["canopy_overhang_pct"],
            hardscape_pct=results["hardscape_pct"],
            shadow_pct=results["shadow_pct"],
            image_url=url_z21, image_zoom=21,
            image_width=width, image_height=height,
            raw_results=results,
            error_message=None,
        )

    async def bulk_analyze(
        self, organization_id: str, wf_ids: Optional[list[str]] = None, force: bool = False
    ) -> dict:
        if wf_ids:
            result = await self.db.execute(
                select(WaterFeature).where(
                    WaterFeature.organization_id == organization_id,
                    WaterFeature.id.in_(wf_ids),
                    WaterFeature.water_type == "pool",
                    WaterFeature.is_active == True,
                )
            )
        else:
            result = await self.db.execute(
                select(WaterFeature)
                .join(Property, WaterFeature.property_id == Property.id)
                .where(
                    WaterFeature.organization_id == organization_id,
                    WaterFeature.water_type == "pool",
                    WaterFeature.is_active == True,
                    Property.is_active == True,
                    Property.lat.isnot(None),
                    Property.lng.isnot(None),
                )
            )
        wfs = result.scalars().all()

        analyzed, skipped, failed = [], 0, 0
        for wf in wfs:
            try:
                analysis = await self.analyze_bow(organization_id, wf.id, force=force)
                if analysis.error_message:
                    failed += 1
                else:
                    analyzed.append(analysis)
            except Exception as e:
                logger.error(f"Bulk analysis failed for WF {wf.id}: {e}")
                failed += 1

        await self.db.flush()
        return {
            "total": len(wfs),
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

    # --- Claude call (multi-image) ---

    def _parse_json(self, text: str) -> dict:
        s = text.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1]
            if s.endswith("```"):
                s = s[:-3].strip()
        match = re.search(r"\{[\s\S]*\}", s)
        if match:
            s = match.group(0)
        s = re.sub(r",\s*([}\]])", r"\1", s)
        return json.loads(s)

    async def _call_claude(self, images: list[bytes], text: str) -> dict:
        content = []
        for img_bytes in images:
            image_b64 = base64.b64encode(img_bytes).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
            })
        content.append({"type": "text", "text": text})

        message = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        response = message.content[0].text.strip()
        return self._parse_json(response)

    async def _measure_pool(
        self, image_z21: bytes, image_z20: Optional[bytes],
        address: str, lat: float, width: int, height: int,
    ) -> dict:
        scale_z21 = self._scale_info(lat, 21, width, height)
        scale_z20 = self._scale_info(lat, 20, width, height)

        prompt = MEASURE_PROMPT.format(
            width=width, height=height,
            ft_per_px_z21=scale_z21["ft_per_px"],
            sqft_per_px_z21=scale_z21["sqft_per_px"],
            img_width_ft_z21=scale_z21["img_width_ft"],
            img_height_ft_z21=scale_z21["img_height_ft"],
            car_px_z21=scale_z21["car_px"],
            ft_per_px_z20=scale_z20["ft_per_px"],
            sqft_per_px_z20=scale_z20["sqft_per_px"],
            img_width_ft_z20=scale_z20["img_width_ft"],
            img_height_ft_z20=scale_z20["img_height_ft"],
        )

        images = [image_z21]
        if image_z20:
            images.append(image_z20)

        result = await self._call_claude(
            images,
            f"Property address: {address}\n\n{prompt}",
        )

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
        self, organization_id: str, property_id: str, wf_id: str,
        existing: Optional[SatelliteAnalysis],
        error_message: str, image_url: str, zoom: int, width: int, height: int,
    ) -> SatelliteAnalysis:
        return await self._save_analysis(
            organization_id, property_id, wf_id, existing,
            error_message=error_message,
            image_url=image_url, image_zoom=zoom,
            image_width=width, image_height=height,
        )

    async def _save_analysis(
        self, organization_id: str, property_id: str, wf_id: str,
        existing: Optional[SatelliteAnalysis], **kwargs
    ) -> SatelliteAnalysis:
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            existing.analysis_version = "5.0"
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        analysis = SatelliteAnalysis(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            property_id=property_id,
            water_feature_id=wf_id,
            **kwargs,
        )
        self.db.add(analysis)
        await self.db.flush()
        await self.db.refresh(analysis)
        return analysis

