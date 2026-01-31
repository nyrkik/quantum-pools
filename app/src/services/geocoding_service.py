"""Geocoding service — OSM primary, Google fallback, DB cache."""

import hashlib
import logging
import asyncio
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.geocode_cache import GeocodeCache
from src.core.config import settings

logger = logging.getLogger(__name__)

# Rate limit: 1 request per second for OSM
_osm_last_request = 0.0


class GeocodingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def geocode(self, address: str) -> Optional[Tuple[float, float, str]]:
        """Geocode an address. Returns (lat, lng, provider) or None."""
        address_hash = hashlib.sha256(address.lower().strip().encode()).hexdigest()

        # Check cache
        result = await self.db.execute(
            select(GeocodeCache).where(GeocodeCache.address_hash == address_hash)
        )
        cached = result.scalar_one_or_none()
        if cached:
            return cached.lat, cached.lng, cached.provider

        # Try OSM first
        coords = await self._geocode_osm(address)
        if coords:
            await self._cache_result(address_hash, address, coords[0], coords[1], "osm")
            return coords[0], coords[1], "osm"

        # Fallback to Google
        if settings.google_maps_api_key:
            coords = await self._geocode_google(address)
            if coords:
                await self._cache_result(address_hash, address, coords[0], coords[1], "google")
                return coords[0], coords[1], "google"

        return None

    async def _geocode_osm(self, address: str) -> Optional[Tuple[float, float]]:
        global _osm_last_request
        import time
        import aiohttp

        # Rate limit
        now = time.time()
        wait = 1.0 - (now - _osm_last_request)
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": address, "format": "json", "limit": 1},
                    headers={"User-Agent": "QuantumPools/1.0"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _osm_last_request = time.time()
                    if resp.status == 200:
                        data = await resp.json()
                        if data:
                            return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            logger.warning(f"OSM geocoding failed for '{address}': {e}")
        return None

    async def _geocode_google(self, address: str) -> Optional[Tuple[float, float]]:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": address, "key": settings.google_maps_api_key},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("results"):
                            loc = data["results"][0]["geometry"]["location"]
                            return loc["lat"], loc["lng"]
        except Exception as e:
            logger.warning(f"Google geocoding failed for '{address}': {e}")
        return None

    async def _cache_result(
        self, address_hash: str, address: str, lat: float, lng: float, provider: str
    ) -> None:
        import uuid
        cache = GeocodeCache(
            id=str(uuid.uuid4()),
            address_hash=address_hash,
            address=address,
            lat=lat,
            lng=lng,
            provider=provider,
        )
        self.db.add(cache)
        await self.db.flush()
