"""
Routing service for calculating real driving distances and times.
Supports multiple providers: OSRM (free), Google Maps (paid), Mapbox (paid).
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Optional
import logging
import asyncio
import aiohttp
import math
from app.config import settings

logger = logging.getLogger(__name__)


class RoutingProvider(ABC):
    """Abstract base class for routing providers."""

    @abstractmethod
    async def get_distance_matrix(
        self,
        locations: List[Tuple[float, float]]
    ) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Get distance and time matrices for a list of locations.

        Args:
            locations: List of (latitude, longitude) tuples

        Returns:
            Tuple of (distance_matrix in meters, time_matrix in minutes)
        """
        pass

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate straight-line distance between two GPS coordinates in miles.
        Used as fallback when routing API fails.

        Args:
            lat1, lon1: First location coordinates
            lat2, lon2: Second location coordinates

        Returns:
            Distance in miles
        """
        R = 3959  # Earth radius in miles

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _create_fallback_matrices(
        self,
        locations: List[Tuple[float, float]]
    ) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Create distance and time matrices using straight-line Haversine distance.
        Used as fallback when routing API is unavailable.

        Args:
            locations: List of (latitude, longitude) tuples

        Returns:
            Tuple of (distance_matrix in meters, time_matrix in minutes)
        """
        num_locations = len(locations)
        distance_matrix = [[0] * num_locations for _ in range(num_locations)]
        time_matrix = [[0] * num_locations for _ in range(num_locations)]

        avg_speed_mph = 30.0

        for i in range(num_locations):
            for j in range(num_locations):
                if i != j:
                    distance_miles = self._haversine_distance(
                        locations[i][0], locations[i][1],
                        locations[j][0], locations[j][1]
                    )
                    # Convert to meters
                    distance_matrix[i][j] = int(distance_miles * 1609.34)

                    # Calculate time in minutes
                    time_hours = distance_miles / avg_speed_mph
                    time_matrix[i][j] = int(time_hours * 60)

        return distance_matrix, time_matrix


class OSRMProvider(RoutingProvider):
    """OSRM (Open Source Routing Machine) provider for driving distances."""

    def __init__(self, base_url: str = "http://router.project-osrm.org"):
        """
        Initialize OSRM provider.

        Args:
            base_url: OSRM server URL (default: public demo server)
        """
        self.base_url = base_url
        self.max_locations_per_request = 100  # OSRM limit

    async def get_distance_matrix(
        self,
        locations: List[Tuple[float, float]]
    ) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Get distance and time matrices using OSRM table service.

        Args:
            locations: List of (latitude, longitude) tuples

        Returns:
            Tuple of (distance_matrix in meters, time_matrix in minutes)
        """
        if len(locations) > self.max_locations_per_request:
            logger.warning(
                f"OSRM request has {len(locations)} locations, "
                f"exceeds max {self.max_locations_per_request}. Using fallback."
            )
            return self._create_fallback_matrices(locations)

        try:
            # Build coordinates string: "lon,lat;lon,lat;..."
            coords_str = ";".join([f"{lon},{lat}" for lat, lon in locations])
            url = f"{self.base_url}/table/v1/driving/{coords_str}"

            params = {
                "annotations": "distance,duration"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        logger.error(f"OSRM API error: {response.status}")
                        return self._create_fallback_matrices(locations)

                    data = await response.json()

                    if data.get("code") != "Ok":
                        logger.error(f"OSRM response error: {data.get('message')}")
                        return self._create_fallback_matrices(locations)

                    # Extract distance matrix (in meters)
                    distance_matrix = data["distances"]

                    # Extract duration matrix (in seconds), convert to minutes
                    durations = data["durations"]
                    time_matrix = [[int(d / 60) for d in row] for row in durations]

                    logger.info(
                        f"OSRM: Retrieved distance matrix for {len(locations)} locations"
                    )

                    return distance_matrix, time_matrix

        except asyncio.TimeoutError:
            logger.error("OSRM request timed out, using fallback")
            return self._create_fallback_matrices(locations)
        except Exception as e:
            logger.error(f"OSRM error: {e}, using fallback")
            return self._create_fallback_matrices(locations)


class GoogleMapsProvider(RoutingProvider):
    """Google Maps Distance Matrix API provider (for future use)."""

    def __init__(self, api_key: str):
        """
        Initialize Google Maps provider.

        Args:
            api_key: Google Maps API key
        """
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        self.max_locations_per_request = 25  # Google Maps limit

    async def get_distance_matrix(
        self,
        locations: List[Tuple[float, float]]
    ) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Get distance and time matrices using Google Maps Distance Matrix API.

        Args:
            locations: List of (latitude, longitude) tuples

        Returns:
            Tuple of (distance_matrix in meters, time_matrix in minutes)
        """
        # TODO: Implement Google Maps Distance Matrix API
        # For now, use fallback
        logger.warning("Google Maps provider not yet implemented, using fallback")
        return self._create_fallback_matrices(locations)


class RoutingService:
    """
    Main routing service that manages different providers.
    Automatically selects best available provider based on config.
    """

    def __init__(self):
        """Initialize routing service with configured provider."""
        self.provider = self._initialize_provider()

    def _initialize_provider(self) -> RoutingProvider:
        """
        Initialize the appropriate routing provider based on configuration.

        Returns:
            Configured routing provider
        """
        # Check if Google Maps is configured and preferred
        if hasattr(settings, 'routing_provider'):
            if settings.routing_provider == "google" and settings.google_maps_api_key:
                logger.info("Using Google Maps routing provider")
                return GoogleMapsProvider(settings.google_maps_api_key)

        # Default to OSRM (free, no API key required)
        logger.info("Using OSRM routing provider (free)")
        osrm_url = getattr(settings, 'osrm_server_url', "http://router.project-osrm.org")
        return OSRMProvider(osrm_url)

    async def get_distance_matrix(
        self,
        locations: List[Tuple[float, float]]
    ) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Get distance and time matrices for a list of locations.

        Args:
            locations: List of (latitude, longitude) tuples

        Returns:
            Tuple of (distance_matrix in meters, time_matrix in minutes)
        """
        return await self.provider.get_distance_matrix(locations)


# Global routing service instance
routing_service = RoutingService()
