"""Satellite analysis service — Google Maps Static API + OpenCV pool/vegetation detection."""

import io
import uuid
import logging
import math
from typing import Optional

import aiohttp
import cv2
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import NotFoundError
from src.models.satellite_analysis import SatelliteAnalysis
from src.models.property import Property

logger = logging.getLogger(__name__)

# Meters per pixel at zoom 20 at equator — adjusted by cos(lat) for actual location
METERS_PER_PIXEL_Z20 = 0.149

# Analysis constants
POOL_HSV_LOWER = np.array([90, 40, 80])
POOL_HSV_UPPER = np.array([130, 255, 255])
VEGETATION_HSV_LOWER = np.array([30, 30, 30])
VEGETATION_HSV_UPPER = np.array([90, 255, 200])
SHADOW_VALUE_THRESHOLD = 60
MIN_POOL_AREA_PX = 200
BUFFER_ZONE_PX = 40


class SatelliteService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

        # Get property
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

        # Check for existing analysis
        existing = await self.get_analysis(organization_id, property_id)
        if existing and not force:
            return existing

        # Fetch satellite image
        zoom = 20
        width, height = 640, 640
        image_url = self._build_image_url(prop.lat, prop.lng, zoom, width, height)
        image_bytes = await self._fetch_image(image_url)

        if not image_bytes:
            return await self._save_analysis(
                organization_id, property_id, existing,
                error_message="Failed to fetch satellite image",
                image_url=image_url, image_zoom=zoom, image_width=width, image_height=height,
            )

        # Run CV analysis
        try:
            results = self._analyze_image(image_bytes, prop.lat, zoom)
        except Exception as e:
            logger.error(f"CV analysis failed for property {property_id}: {e}")
            return await self._save_analysis(
                organization_id, property_id, existing,
                error_message=f"Analysis failed: {e}",
                image_url=image_url, image_zoom=zoom, image_width=width, image_height=height,
            )

        # Update property pool_sqft if detected and not already set
        if results["pool_detected"] and results["estimated_pool_sqft"] and not prop.pool_sqft:
            prop.pool_sqft = results["estimated_pool_sqft"]

        return await self._save_analysis(
            organization_id, property_id, existing,
            pool_detected=results["pool_detected"],
            estimated_pool_sqft=results["estimated_pool_sqft"],
            pool_contour_points=results["pool_contour_points"],
            pool_confidence=results["pool_confidence"],
            vegetation_pct=results["vegetation_pct"],
            canopy_overhang_pct=results["canopy_overhang_pct"],
            hardscape_pct=results["hardscape_pct"],
            shadow_pct=results["shadow_pct"],
            image_url=image_url, image_zoom=zoom, image_width=width, image_height=height,
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

    def _analyze_image(self, image_bytes: bytes, lat: float, zoom: int) -> dict:
        img_array = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image")

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        total_pixels = img.shape[0] * img.shape[1]

        # Meters per pixel at this latitude and zoom
        mpp = METERS_PER_PIXEL_Z20 * (2 ** (20 - zoom)) / math.cos(math.radians(lat))
        sqm_per_pixel = mpp * mpp
        sqft_per_pixel = sqm_per_pixel * 10.7639

        # Pool detection (blue/cyan regions)
        pool_mask = cv2.inRange(hsv, POOL_HSV_LOWER, POOL_HSV_UPPER)
        pool_mask = cv2.morphologyEx(pool_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        pool_mask = cv2.morphologyEx(pool_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        contours, _ = cv2.findContours(pool_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        pool_detected = False
        estimated_pool_sqft = None
        pool_contour_points = None
        pool_confidence = 0.0
        best_contour = None
        best_area = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < MIN_POOL_AREA_PX:
                continue

            # Shape analysis — pools are roughly convex
            hull = cv2.convexHull(contour)
            hull_area = cv2.contourArea(hull)
            if hull_area == 0:
                continue
            solidity = area / hull_area

            # Pools typically have solidity > 0.6
            if solidity < 0.5:
                continue

            if area > best_area:
                best_area = area
                best_contour = contour

        if best_contour is not None and best_area >= MIN_POOL_AREA_PX:
            pool_detected = True
            estimated_pool_sqft = round(best_area * sqft_per_pixel, 1)

            # Confidence based on area and solidity
            hull = cv2.convexHull(best_contour)
            hull_area = cv2.contourArea(hull)
            solidity = best_area / hull_area if hull_area > 0 else 0

            # Confidence: area contribution (bigger = more confident) + shape contribution
            area_conf = min(best_area / 2000, 0.5)
            shape_conf = solidity * 0.5
            pool_confidence = round(min(area_conf + shape_conf, 1.0), 3)

            # Store simplified contour points
            epsilon = 0.02 * cv2.arcLength(best_contour, True)
            approx = cv2.approxPolyDP(best_contour, epsilon, True)
            pool_contour_points = approx.reshape(-1, 2).tolist()

        # Create pool mask for overhang detection
        final_pool_mask = np.zeros(pool_mask.shape, dtype=np.uint8)
        if best_contour is not None:
            cv2.drawContours(final_pool_mask, [best_contour], -1, 255, -1)

        # Vegetation detection (green regions)
        veg_mask = cv2.inRange(hsv, VEGETATION_HSV_LOWER, VEGETATION_HSV_UPPER)
        veg_mask = cv2.morphologyEx(veg_mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        vegetation_pct = round(np.count_nonzero(veg_mask) / total_pixels * 100, 1)

        # Canopy overhang — vegetation within buffer zone of pool
        canopy_overhang_pct = 0.0
        if pool_detected:
            dilated_pool = cv2.dilate(final_pool_mask, np.ones((BUFFER_ZONE_PX, BUFFER_ZONE_PX), np.uint8))
            buffer_zone = cv2.subtract(dilated_pool, final_pool_mask)
            buffer_pixels = np.count_nonzero(buffer_zone)
            if buffer_pixels > 0:
                overhang_pixels = np.count_nonzero(cv2.bitwise_and(veg_mask, buffer_zone))
                canopy_overhang_pct = round(overhang_pixels / buffer_pixels * 100, 1)

        # Shadow detection (dark areas)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        shadow_mask = (gray < SHADOW_VALUE_THRESHOLD).astype(np.uint8) * 255
        # Exclude pool from shadow count
        if pool_detected:
            shadow_mask = cv2.bitwise_and(shadow_mask, cv2.bitwise_not(final_pool_mask))
        shadow_pct = round(np.count_nonzero(shadow_mask) / total_pixels * 100, 1)

        # Hardscape — not pool, not vegetation, not shadow
        non_hardscape = cv2.bitwise_or(veg_mask, shadow_mask)
        if pool_detected:
            non_hardscape = cv2.bitwise_or(non_hardscape, final_pool_mask)
        hardscape_pct = round((1 - np.count_nonzero(non_hardscape) / total_pixels) * 100, 1)

        return {
            "pool_detected": pool_detected,
            "estimated_pool_sqft": estimated_pool_sqft,
            "pool_contour_points": pool_contour_points,
            "pool_confidence": pool_confidence,
            "vegetation_pct": vegetation_pct,
            "canopy_overhang_pct": canopy_overhang_pct,
            "hardscape_pct": hardscape_pct,
            "shadow_pct": shadow_pct,
        }

    async def _save_analysis(
        self, organization_id: str, property_id: str,
        existing: Optional[SatelliteAnalysis], **kwargs
    ) -> SatelliteAnalysis:
        if existing:
            for key, value in kwargs.items():
                if value is not None:
                    setattr(existing, key, value)
            existing.analysis_version = "1.0"
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
