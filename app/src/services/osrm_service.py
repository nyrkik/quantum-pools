"""OSRM service — fetch driving polylines from public OSRM demo server."""

import hashlib
import json
import logging
from typing import List, Tuple

import httpx

from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

OSRM_BASE = "https://router.project-osrm.org"
CACHE_TTL = 86400  # 24 hours


def _cache_key(coordinates: List[Tuple[float, float]]) -> str:
    raw = ";".join(f"{lng},{lat}" for lat, lng in coordinates)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"osrm:route:{h}"


async def get_route_polyline(
    coordinates: List[Tuple[float, float]],
) -> dict:
    """
    Fetch a driving route polyline from OSRM.

    Args:
        coordinates: List of (lat, lng) tuples in visit order.

    Returns:
        {"polyline": [[lat, lng], ...], "distance_meters": int, "duration_seconds": int}
    """
    if len(coordinates) < 2:
        return {"polyline": [], "distance_meters": 0, "duration_seconds": 0}

    cache_k = _cache_key(coordinates)

    # Check cache
    redis = await get_redis()
    if redis:
        cached = await redis.get(cache_k)
        if cached:
            return json.loads(cached)

    # Build OSRM URL — expects lon,lat order
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coordinates)
    url = f"{OSRM_BASE}/route/v1/driving/{coord_str}?overview=full&geometries=geojson"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            logger.warning(f"OSRM returned no route: {data.get('code')}")
            return {"polyline": [], "distance_meters": 0, "duration_seconds": 0}

        route = data["routes"][0]
        # GeoJSON coordinates are [lng, lat] — flip to [lat, lng]
        geojson_coords = route["geometry"]["coordinates"]
        polyline = [[c[1], c[0]] for c in geojson_coords]

        result = {
            "polyline": polyline,
            "distance_meters": int(route["distance"]),
            "duration_seconds": int(route["duration"]),
        }

        # Cache result
        if redis:
            await redis.setex(cache_k, CACHE_TTL, json.dumps(result))

        return result

    except Exception as e:
        logger.error(f"OSRM request failed: {e}")
        return {"polyline": [], "distance_meters": 0, "duration_seconds": 0}
