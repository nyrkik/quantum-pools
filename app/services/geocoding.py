"""
Geocoding service for converting addresses to GPS coordinates.
Uses OpenStreetMap Nominatim (free) by default, with Google Maps API as optional upgrade.
"""

from geopy.geocoders import Nominatim, GoogleV3
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from typing import Optional, Tuple
import logging
import asyncio

from app.config import settings

logger = logging.getLogger(__name__)


class GeocodingService:
    """Service for geocoding addresses to latitude/longitude coordinates."""

    def __init__(self):
        """Initialize geocoding service with appropriate provider."""
        if settings.google_maps_api_key:
            # Use Google Maps if API key is provided
            self.geocoder = GoogleV3(api_key=settings.google_maps_api_key)
            self.provider = "Google Maps"
        else:
            # Use free OpenStreetMap Nominatim
            self.geocoder = Nominatim(
                user_agent="QuantumPools/0.1.0",
                timeout=10
            )
            self.provider = "OpenStreetMap Nominatim"
            logger.info(
                "Using OpenStreetMap Nominatim for geocoding (rate limited to 1 req/sec). "
                "Set GOOGLE_MAPS_API_KEY for production use."
            )

    async def geocode_address(
        self,
        address: str,
        retry_count: int = 3
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode an address to latitude/longitude coordinates.

        Args:
            address: Street address to geocode
            retry_count: Number of retries on timeout (default: 3)

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails

        Note:
            OpenStreetMap Nominatim has a rate limit of 1 request per second.
            For bulk geocoding, add delays between requests or use Google Maps API.
        """
        for attempt in range(retry_count):
            try:
                # Run geocoding in thread pool to avoid blocking
                location = await asyncio.to_thread(
                    self.geocoder.geocode,
                    address
                )

                if location:
                    logger.info(
                        f"Geocoded '{address}' to ({location.latitude}, {location.longitude}) "
                        f"using {self.provider}"
                    )
                    return (location.latitude, location.longitude)
                else:
                    logger.warning(
                        f"No geocoding results found for address: {address}"
                    )
                    return None

            except GeocoderTimedOut:
                if attempt < retry_count - 1:
                    logger.warning(
                        f"Geocoding timeout for '{address}', "
                        f"retrying ({attempt + 1}/{retry_count})..."
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error(
                        f"Geocoding failed after {retry_count} attempts for: {address}"
                    )
                    return None

            except GeocoderServiceError as e:
                logger.error(f"Geocoding service error for '{address}': {str(e)}")
                return None

            except Exception as e:
                logger.error(f"Unexpected error geocoding '{address}': {str(e)}")
                return None

        return None

    async def geocode_with_rate_limit(
        self,
        address: str,
        delay_seconds: float = 1.0
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode address with rate limiting delay.

        Use this method when geocoding multiple addresses in sequence
        to respect OpenStreetMap Nominatim's 1 req/sec rate limit.

        Args:
            address: Street address to geocode
            delay_seconds: Delay before geocoding (default: 1.0 for Nominatim)

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not settings.google_maps_api_key:
            # Only apply delay for OpenStreetMap (rate limited)
            await asyncio.sleep(delay_seconds)

        return await self.geocode_address(address)


# Global geocoding service instance
geocoding_service = GeocodingService()
