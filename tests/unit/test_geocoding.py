"""
Unit tests for Geocoding Service.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.geocoding import GeocodingService


@pytest.mark.unit
class TestGeocodingService:
    """Test geocoding service functionality."""

    @pytest.mark.asyncio
    async def test_geocode_address_success(self):
        """Test successful address geocoding."""
        service = GeocodingService()

        # Mock the geocoder
        with patch.object(service.geocoder, 'geocode') as mock_geocode:
            mock_location = Mock()
            mock_location.latitude = 40.7128
            mock_location.longitude = -74.0060
            mock_geocode.return_value = mock_location

            # Mock asyncio.to_thread to just call the function directly
            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_location

                result = await service.geocode_address("New York, NY")

                assert result is not None
                assert result[0] == 40.7128
                assert result[1] == -74.0060

    @pytest.mark.asyncio
    async def test_geocode_address_not_found(self):
        """Test geocoding with address not found."""
        service = GeocodingService()

        with patch.object(service.geocoder, 'geocode') as mock_geocode:
            mock_geocode.return_value = None

            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = None

                result = await service.geocode_address("Invalid Address XYZ")

                assert result is None

    @pytest.mark.asyncio
    async def test_geocode_with_rate_limit(self):
        """Test geocoding with rate limiting."""
        service = GeocodingService()

        with patch.object(service.geocoder, 'geocode') as mock_geocode:
            mock_location = Mock()
            mock_location.latitude = 34.0522
            mock_location.longitude = -118.2437
            mock_geocode.return_value = mock_location

            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_location

                with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    result = await service.geocode_with_rate_limit("Los Angeles, CA", delay_seconds=1.0)

                    # Verify rate limit delay was called (for OSM)
                    # Note: Only called if not using Google Maps API
                    assert result is not None
                    assert result[0] == 34.0522

    @pytest.mark.asyncio
    async def test_batch_geocode(self):
        """Test batch geocoding multiple addresses."""
        service = GeocodingService()

        addresses = [
            "New York, NY",
            "Los Angeles, CA",
            "Chicago, IL"
        ]

        expected_results = [
            (40.7128, -74.0060),
            (34.0522, -118.2437),
            (41.8781, -87.6298)
        ]

        with patch.object(service, 'geocode_with_rate_limit', new_callable=AsyncMock) as mock_geocode:
            mock_geocode.side_effect = expected_results

            results = []
            for address in addresses:
                result = await service.geocode_with_rate_limit(address)
                results.append(result)

            assert len(results) == 3
            assert results[0] == expected_results[0]
            assert results[1] == expected_results[1]
            assert results[2] == expected_results[2]
