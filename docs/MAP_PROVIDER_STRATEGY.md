# Map Provider Strategy: Geocoding Abstraction & Migration Plan

**Date:** 2025-10-26
**Status:** Foundation Design
**Purpose:** Define geocoding provider abstraction layer and migration from OpenStreetMap to Google Maps

---

## Executive Summary

RouteOptimizer currently uses OpenStreetMap (Nominatim) for geocoding via the geopy library. While sufficient for initial development, this creates vendor lock-in and limits scalability.

**Problem:** Direct Nominatim calls hardcoded throughout codebase → Cannot switch to Google Maps without rewriting all geocoding code.

**Solution:** Provider abstraction layer with factory pattern → Organizations can choose provider, easy migration, fallback support.

**Timeline:**
- **Phase 1 (Now):** Implement abstraction layer, continue using OpenStreetMap
- **Phase 2 (Future):** Migrate Professional/Enterprise tier organizations to Google Maps
- **Phase 3 (Future):** Allow "bring your own API key" for Enterprise customers

---

## Table of Contents

1. [Current State & Problems](#current-state--problems)
2. [Provider Abstraction Design](#provider-abstraction-design)
3. [OpenStreetMap Implementation](#openstreetmap-implementation)
4. [Google Maps Implementation](#google-maps-implementation)
5. [Geocoding Factory](#geocoding-factory)
6. [Per-Organization Provider Configuration](#per-organization-provider-configuration)
7. [Geocoding Metadata Tracking](#geocoding-metadata-tracking)
8. [Geocoding Cache](#geocoding-cache)
9. [Migration Plan: OSM → Google Maps](#migration-plan-osm--google-maps)
10. [Cost Analysis](#cost-analysis)
11. [API Key Management](#api-key-management)

---

## Current State & Problems

### Existing Implementation

**File:** `app/services/geocoding.py`

```python
from geopy.geocoders import Nominatim

async def geocode_address(address: str):
    """Geocode address using Nominatim (OpenStreetMap)."""
    geolocator = Nominatim(user_agent="RouteOptimizer")
    location = geolocator.geocode(address)
    if location:
        return (location.latitude, location.longitude)
    return None
```

### Problems

| Problem | Impact | Severity |
|---------|--------|----------|
| **Hardcoded Nominatim** | Cannot switch providers without rewriting all geocoding code | HIGH |
| **Rate Limits** | 1 request/second → 100 customers = 100 seconds (too slow for batch import) | HIGH |
| **Accuracy Issues** | Nominatim less accurate for commercial addresses than Google Maps | MEDIUM |
| **No Metadata** | Cannot track which provider geocoded each address | MEDIUM |
| **No Caching** | Duplicate addresses geocoded multiple times (wastes API calls) | MEDIUM |
| **No Fallback** | If Nominatim fails, geocoding fails (no retry with alternate provider) | LOW |
| **No Per-Org Config** | All organizations forced to use same provider | LOW |

### Why Abstraction Matters

**Business Reasons:**
- **Competitive Feature:** Offer Google Maps to premium customers (superior accuracy)
- **Cost Optimization:** Route cheap queries to OSM, complex queries to Google
- **Enterprise Sales:** "Bring your own API key" for large customers
- **Risk Mitigation:** Not dependent on single provider's uptime

**Technical Reasons:**
- **Testability:** Mock geocoding in tests without external API calls
- **A/B Testing:** Compare provider accuracy across same addresses
- **Graceful Degradation:** Fallback to alternate provider on failure

---

## Provider Abstraction Design

### Architecture

```
┌─────────────────────┐
│  Geocoding Service  │ ← High-level service (handles caching, retries)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Geocoding Factory  │ ← Selects provider based on org configuration
└──────────┬──────────┘
           │
           ├─────────────────┬─────────────────┐
           ▼                 ▼                 ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ OSM Provider     │  │ Google Provider  │  │ Future: Mapbox   │
│ (implements      │  │ (implements      │  │ (implements      │
│  Geocoding       │  │  Geocoding       │  │  Geocoding       │
│  Provider)       │  │  Provider)       │  │  Provider)       │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### GeocodingProvider Interface

**File:** `app/services/geocoding/interface.py`

```python
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

@dataclass
class GeocodingResult:
    """Standardized geocoding result."""
    latitude: float
    longitude: float
    formatted_address: str
    provider: str
    confidence: float  # 0.0 - 1.0 (provider-specific scoring)
    metadata: Dict  # Provider-specific metadata

class GeocodingProvider(ABC):
    """
    Abstract interface for geocoding providers.
    All providers must implement these methods with consistent behavior.
    """

    @abstractmethod
    async def geocode(self, address: str) -> Optional[GeocodingResult]:
        """
        Convert address string to coordinates.

        Args:
            address: Full address string (e.g., "123 Main St, Sacramento, CA 95814")

        Returns:
            GeocodingResult with coordinates and metadata, or None if geocoding fails

        Raises:
            GeocodingError: For API errors, rate limits, etc.
        """
        pass

    @abstractmethod
    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """
        Convert coordinates to address string.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Formatted address string, or None if reverse geocoding fails

        Raises:
            GeocodingError: For API errors, rate limits, etc.
        """
        pass

    @abstractmethod
    async def batch_geocode(self, addresses: list[str]) -> list[Optional[GeocodingResult]]:
        """
        Geocode multiple addresses (may be more efficient than individual calls).

        Args:
            addresses: List of address strings

        Returns:
            List of GeocodingResults (same order as input, None for failures)

        Notes:
            - Default implementation calls geocode() sequentially
            - Providers with batch APIs should override for efficiency
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name for metadata tracking (e.g., 'openstreetmap', 'google_maps')."""
        pass

    @abstractmethod
    def get_rate_limit(self) -> int:
        """Return requests per second limit (for throttling)."""
        pass
```

**File:** `app/services/geocoding/exceptions.py`

```python
class GeocodingError(Exception):
    """Base exception for geocoding errors."""
    pass

class RateLimitError(GeocodingError):
    """Raised when provider rate limit exceeded."""
    pass

class InvalidAddressError(GeocodingError):
    """Raised when address cannot be geocoded."""
    pass

class ProviderUnavailableError(GeocodingError):
    """Raised when provider API is down."""
    pass
```

---

## OpenStreetMap Implementation

**File:** `app/services/geocoding/openstreetmap.py`

```python
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import asyncio
import logging
from typing import Optional
from .interface import GeocodingProvider, GeocodingResult
from .exceptions import RateLimitError, ProviderUnavailableError

logger = logging.getLogger(__name__)

class OpenStreetMapProvider(GeocodingProvider):
    """
    OpenStreetMap (Nominatim) geocoding provider.

    Rate Limit: 1 request/second (strictly enforced)
    Accuracy: Good for most addresses, less reliable for commercial properties
    Cost: Free (with attribution)
    """

    def __init__(self, user_agent: str = "RouteOptimizer/1.0"):
        self.geocoder = Nominatim(user_agent=user_agent, timeout=10)
        self.last_request_time = 0
        self.rate_limit = 1  # requests per second

    async def geocode(self, address: str) -> Optional[GeocodingResult]:
        """Geocode address using Nominatim."""
        try:
            # Rate limiting (1 req/sec)
            await self._throttle()

            # Geocode (run in executor to avoid blocking)
            location = await asyncio.to_thread(self.geocoder.geocode, address)

            if not location:
                logger.warning(f"OSM geocoding failed for address: {address}")
                return None

            return GeocodingResult(
                latitude=location.latitude,
                longitude=location.longitude,
                formatted_address=location.address,
                provider="openstreetmap",
                confidence=self._calculate_confidence(location),
                metadata={
                    "place_id": location.raw.get("place_id"),
                    "osm_type": location.raw.get("osm_type"),
                    "osm_id": location.raw.get("osm_id"),
                    "display_name": location.raw.get("display_name"),
                }
            )

        except GeocoderTimedOut:
            logger.error(f"OSM geocoding timeout for address: {address}")
            raise ProviderUnavailableError("Nominatim timeout")

        except GeocoderServiceError as e:
            logger.error(f"OSM service error: {e}")
            raise ProviderUnavailableError(f"Nominatim service error: {e}")

        except Exception as e:
            logger.error(f"Unexpected OSM geocoding error: {e}")
            return None

    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Reverse geocode coordinates using Nominatim."""
        try:
            await self._throttle()

            location = await asyncio.to_thread(
                self.geocoder.reverse,
                f"{lat}, {lon}"
            )

            return location.address if location else None

        except Exception as e:
            logger.error(f"OSM reverse geocoding error: {e}")
            return None

    async def batch_geocode(self, addresses: list[str]) -> list[Optional[GeocodingResult]]:
        """
        Batch geocode addresses.
        Nominatim has no batch API, so we throttle individual requests to 1 req/sec.
        """
        results = []
        for address in addresses:
            result = await self.geocode(address)
            results.append(result)
            # Rate limiting handled by _throttle() in geocode()

        return results

    def get_provider_name(self) -> str:
        return "openstreetmap"

    def get_rate_limit(self) -> int:
        return 1  # 1 request per second

    async def _throttle(self):
        """Enforce 1 request/second rate limit."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < 1.0:
            await asyncio.sleep(1.0 - time_since_last)

        self.last_request_time = asyncio.get_event_loop().time()

    def _calculate_confidence(self, location) -> float:
        """
        Calculate confidence score based on OSM metadata.
        Higher score = more confident result.
        """
        # OSM doesn't provide explicit confidence, so we estimate based on type
        osm_type = location.raw.get("type", "").lower()
        category = location.raw.get("class", "").lower()

        # High confidence: specific building/address
        if osm_type in ["house", "building", "address"]:
            return 0.9

        # Medium confidence: street/road
        if category == "highway":
            return 0.7

        # Low confidence: general area (city, county, etc.)
        if osm_type in ["city", "town", "village", "county"]:
            return 0.5

        # Default
        return 0.6
```

---

## Google Maps Implementation

**File:** `app/services/geocoding/google_maps.py`

```python
import googlemaps
import asyncio
import logging
from typing import Optional
from .interface import GeocodingProvider, GeocodingResult
from .exceptions import RateLimitError, ProviderUnavailableError, InvalidAddressError

logger = logging.getLogger(__name__)

class GoogleMapsProvider(GeocodingProvider):
    """
    Google Maps Platform geocoding provider.

    Rate Limit: No strict limit (pay-per-use), but 50 req/sec burst recommended
    Accuracy: Superior for commercial addresses, structured data
    Cost: $5 per 1000 requests (first $200/month free)
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Google Maps API key required")

        self.client = googlemaps.Client(key=api_key, timeout=10)
        self.rate_limit = 50  # Recommended burst limit

    async def geocode(self, address: str) -> Optional[GeocodingResult]:
        """Geocode address using Google Maps Platform."""
        try:
            # Run in executor to avoid blocking
            result = await asyncio.to_thread(
                self.client.geocode,
                address
            )

            if not result or len(result) == 0:
                logger.warning(f"Google Maps geocoding failed for address: {address}")
                return None

            # Google returns list of results, take first (best match)
            first_result = result[0]
            geometry = first_result["geometry"]
            location = geometry["location"]

            return GeocodingResult(
                latitude=location["lat"],
                longitude=location["lng"],
                formatted_address=first_result["formatted_address"],
                provider="google_maps",
                confidence=self._calculate_confidence(geometry),
                metadata={
                    "place_id": first_result.get("place_id"),
                    "types": first_result.get("types", []),
                    "location_type": geometry.get("location_type"),
                    "address_components": first_result.get("address_components", []),
                }
            )

        except googlemaps.exceptions.ApiError as e:
            logger.error(f"Google Maps API error: {e}")
            if "OVER_QUERY_LIMIT" in str(e):
                raise RateLimitError("Google Maps rate limit exceeded")
            raise ProviderUnavailableError(f"Google Maps API error: {e}")

        except googlemaps.exceptions.Timeout:
            logger.error("Google Maps timeout")
            raise ProviderUnavailableError("Google Maps timeout")

        except Exception as e:
            logger.error(f"Unexpected Google Maps error: {e}")
            return None

    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Reverse geocode coordinates using Google Maps."""
        try:
            result = await asyncio.to_thread(
                self.client.reverse_geocode,
                (lat, lon)
            )

            if result and len(result) > 0:
                return result[0]["formatted_address"]

            return None

        except Exception as e:
            logger.error(f"Google Maps reverse geocoding error: {e}")
            return None

    async def batch_geocode(self, addresses: list[str]) -> list[Optional[GeocodingResult]]:
        """
        Batch geocode addresses.
        Google Maps has no official batch API, but we can parallelize requests.
        """
        tasks = [self.geocode(address) for address in addresses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to None
        return [
            result if not isinstance(result, Exception) else None
            for result in results
        ]

    def get_provider_name(self) -> str:
        return "google_maps"

    def get_rate_limit(self) -> int:
        return 50  # requests per second (recommended)

    def _calculate_confidence(self, geometry: dict) -> float:
        """
        Calculate confidence based on Google's location_type.
        https://developers.google.com/maps/documentation/geocoding/overview#Results
        """
        location_type = geometry.get("location_type", "")

        confidence_map = {
            "ROOFTOP": 1.0,  # Exact address (highest accuracy)
            "RANGE_INTERPOLATED": 0.8,  # Interpolated between two addresses
            "GEOMETRIC_CENTER": 0.6,  # Center of polyline (street) or polygon (area)
            "APPROXIMATE": 0.4,  # Approximate location
        }

        return confidence_map.get(location_type, 0.5)
```

---

## Geocoding Factory

**File:** `app/services/geocoding/factory.py`

```python
from typing import Optional
from app.models.organization import Organization
from .interface import GeocodingProvider
from .openstreetmap import OpenStreetMapProvider
from .google_maps import GoogleMapsProvider
import logging

logger = logging.getLogger(__name__)

class GeocodingFactory:
    """
    Factory for creating geocoding provider instances.
    Selects provider based on organization configuration.
    """

    @staticmethod
    def get_provider(organization: Optional[Organization] = None) -> GeocodingProvider:
        """
        Get geocoding provider for organization.

        Provider selection logic:
        1. If org.default_map_provider == "google_maps" AND has API key → Google Maps
        2. Otherwise → OpenStreetMap (free, no API key required)

        Args:
            organization: Organization requesting geocoding (None = use OSM default)

        Returns:
            GeocodingProvider instance
        """

        # Default to OpenStreetMap if no org specified
        if not organization:
            logger.debug("No organization specified, using OpenStreetMap")
            return OpenStreetMapProvider()

        # Check if org configured for Google Maps
        if organization.default_map_provider == "google_maps":
            # Verify API key exists
            api_key = organization.google_maps_api_key
            if api_key:
                logger.debug(f"Using Google Maps for org {organization.id}")
                return GoogleMapsProvider(api_key=api_key)
            else:
                logger.warning(
                    f"Org {organization.id} configured for Google Maps but no API key found. "
                    f"Falling back to OpenStreetMap."
                )
                return OpenStreetMapProvider()

        # Default to OpenStreetMap
        logger.debug(f"Using OpenStreetMap for org {organization.id}")
        return OpenStreetMapProvider()

    @staticmethod
    def get_provider_by_name(provider_name: str, api_key: Optional[str] = None) -> GeocodingProvider:
        """
        Get provider by name (for testing, migrations, etc.).

        Args:
            provider_name: "openstreetmap" or "google_maps"
            api_key: API key (required for Google Maps)

        Returns:
            GeocodingProvider instance
        """
        if provider_name == "google_maps":
            if not api_key:
                raise ValueError("API key required for Google Maps")
            return GoogleMapsProvider(api_key=api_key)

        elif provider_name == "openstreetmap":
            return OpenStreetMapProvider()

        else:
            raise ValueError(f"Unknown provider: {provider_name}")
```

---

## Per-Organization Provider Configuration

### Database Schema

**organizations table additions:**

```sql
-- Already in SAAS_ARCHITECTURE.md
ALTER TABLE organizations ADD COLUMN default_map_provider VARCHAR(50) DEFAULT 'openstreetmap';
ALTER TABLE organizations ADD COLUMN google_maps_api_key VARCHAR(200);  -- Encrypted

CREATE INDEX idx_orgs_map_provider ON organizations(default_map_provider);
```

**customers/drivers table additions:**

```sql
ALTER TABLE customers ADD COLUMN geocoding_provider VARCHAR(50);
ALTER TABLE customers ADD COLUMN geocoded_by UUID REFERENCES users(id);
ALTER TABLE customers ADD COLUMN geocoded_at TIMESTAMP;

ALTER TABLE drivers ADD COLUMN geocoding_provider VARCHAR(50);
ALTER TABLE drivers ADD COLUMN geocoded_by UUID REFERENCES users(id);
ALTER TABLE drivers ADD COLUMN geocoded_at TIMESTAMP;

CREATE INDEX idx_customers_geocoding_provider ON customers(geocoding_provider);
CREATE INDEX idx_drivers_geocoding_provider ON drivers(geocoding_provider);
```

### Updated Geocoding Service

**File:** `app/services/geocoding.py`

```python
from typing import Optional, Tuple
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.organization import Organization
from app.models.customer import Customer
from .geocoding.factory import GeocodingFactory
from .geocoding.interface import GeocodingResult
import logging

logger = logging.getLogger(__name__)

class GeocodingService:
    """
    High-level geocoding service with caching, retry logic, and metadata tracking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def geocode_customer_address(
        self,
        customer: Customer,
        organization: Organization,
        geocoded_by_user_id: Optional[UUID] = None,
        force_re_geocode: bool = False
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode customer address using organization's configured provider.

        Args:
            customer: Customer to geocode
            organization: Organization (determines provider)
            geocoded_by_user_id: User who triggered geocoding
            force_re_geocode: Re-geocode even if already geocoded

        Returns:
            (latitude, longitude) tuple, or None if geocoding failed
        """

        # Skip if already geocoded (unless forced)
        if not force_re_geocode and customer.latitude and customer.longitude:
            logger.debug(f"Customer {customer.id} already geocoded, skipping")
            return (customer.latitude, customer.longitude)

        # Check geocoding cache first
        cached = await self._check_cache(customer.address)
        if cached:
            logger.debug(f"Using cached geocoding for address: {customer.address}")
            await self._update_customer_geocoding(customer, cached, geocoded_by_user_id)
            return (cached.latitude, cached.longitude)

        # Get provider
        provider = GeocodingFactory.get_provider(organization)

        # Geocode
        try:
            result = await provider.geocode(customer.address)

            if result:
                # Cache result
                await self._cache_result(customer.address, result)

                # Update customer
                await self._update_customer_geocoding(customer, result, geocoded_by_user_id)

                logger.info(
                    f"Successfully geocoded customer {customer.id} using {result.provider} "
                    f"(confidence: {result.confidence:.2f})"
                )

                return (result.latitude, result.longitude)

            else:
                logger.warning(f"Geocoding failed for customer {customer.id}: {customer.address}")
                return None

        except Exception as e:
            logger.error(f"Geocoding error for customer {customer.id}: {e}")
            return None

    async def _update_customer_geocoding(
        self,
        customer: Customer,
        result: GeocodingResult,
        geocoded_by: Optional[UUID]
    ):
        """Update customer with geocoding result and metadata."""
        customer.latitude = result.latitude
        customer.longitude = result.longitude
        customer.geocoding_provider = result.provider
        customer.geocoded_by = geocoded_by
        customer.geocoded_at = datetime.utcnow()
        await self.db.commit()

    async def _check_cache(self, address: str) -> Optional[GeocodingResult]:
        """Check geocoding cache for address."""
        # Implementation in next section
        pass

    async def _cache_result(self, address: str, result: GeocodingResult):
        """Cache geocoding result."""
        # Implementation in next section
        pass
```

---

## Geocoding Metadata Tracking

### Purpose

Track metadata about geocoding operations:
- **Which provider** geocoded each address (for re-geocoding during migrations)
- **Who triggered** geocoding (user accountability)
- **When** geocoding occurred (audit trail)

### Usage

**Identify addresses needing re-geocoding:**

```sql
-- Find all customers geocoded with OpenStreetMap (for migration to Google Maps)
SELECT id, display_name, address, geocoded_at
FROM customers
WHERE organization_id = '{org_id}'
  AND geocoding_provider = 'openstreetmap'
ORDER BY geocoded_at DESC;
```

**Audit geocoding activity:**

```sql
-- Find all geocoding operations by specific user
SELECT c.id, c.display_name, c.address, c.geocoded_at, u.email
FROM customers c
JOIN users u ON c.geocoded_by = u.id
WHERE c.organization_id = '{org_id}'
  AND c.geocoded_by = '{user_id}'
ORDER BY c.geocoded_at DESC;
```

---

## Geocoding Cache

### Purpose

Reduce API calls and costs by caching geocoding results for identical addresses.

**Example:** 10 customers at "123 Main St, Sacramento, CA" → Geocode once, reuse result 10 times.

### Database Schema

```sql
CREATE TABLE geocoding_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    address_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA256(normalized_address)
    normalized_address TEXT NOT NULL,  -- Lowercase, trimmed, standardized
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    formatted_address TEXT,
    provider VARCHAR(50) NOT NULL,
    confidence FLOAT,
    metadata JSONB,

    -- Cache management
    hit_count INTEGER DEFAULT 1,  -- How many times this cache entry was used
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_geocoding_cache_hash ON geocoding_cache(address_hash);
CREATE INDEX idx_geocoding_cache_provider ON geocoding_cache(provider);
CREATE INDEX idx_geocoding_cache_last_used ON geocoding_cache(last_used_at);
```

### Implementation

```python
# app/services/geocoding.py (additions)
import hashlib

class GeocodingService:
    # ... (existing methods)

    async def _check_cache(self, address: str) -> Optional[GeocodingResult]:
        """Check geocoding cache for address."""
        address_hash = self._hash_address(address)

        result = await self.db.execute(
            select(GeocodingCache).where(GeocodingCache.address_hash == address_hash)
        )
        cache_entry = result.scalar_one_or_none()

        if cache_entry:
            # Update hit count and last used
            cache_entry.hit_count += 1
            cache_entry.last_used_at = datetime.utcnow()
            await self.db.commit()

            return GeocodingResult(
                latitude=cache_entry.latitude,
                longitude=cache_entry.longitude,
                formatted_address=cache_entry.formatted_address,
                provider=cache_entry.provider,
                confidence=cache_entry.confidence,
                metadata=cache_entry.metadata or {}
            )

        return None

    async def _cache_result(self, address: str, result: GeocodingResult):
        """Cache geocoding result."""
        address_hash = self._hash_address(address)
        normalized = self._normalize_address(address)

        cache_entry = GeocodingCache(
            address_hash=address_hash,
            normalized_address=normalized,
            latitude=result.latitude,
            longitude=result.longitude,
            formatted_address=result.formatted_address,
            provider=result.provider,
            confidence=result.confidence,
            metadata=result.metadata
        )

        self.db.add(cache_entry)
        await self.db.commit()

    def _hash_address(self, address: str) -> str:
        """Generate SHA256 hash of normalized address."""
        normalized = self._normalize_address(address)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _normalize_address(self, address: str) -> str:
        """Normalize address for caching (lowercase, trim, remove extra spaces)."""
        return " ".join(address.lower().split())
```

### Cache Invalidation

**Strategy:** Time-based expiration (addresses don't change, so cache can be long-lived)

```python
# Background job (run daily)
async def clean_geocoding_cache(db: AsyncSession):
    """Remove cache entries not used in 90 days."""
    cutoff_date = datetime.utcnow() - timedelta(days=90)

    await db.execute(
        delete(GeocodingCache).where(GeocodingCache.last_used_at < cutoff_date)
    )
    await db.commit()
```

---

## Migration Plan: OSM → Google Maps

### Scenario 1: Migrate Organization to Google Maps

**When:** Organization upgrades from Starter to Professional tier (includes Google Maps)

**Steps:**

1. **Update Organization Configuration**
```python
# Admin updates org settings
organization.default_map_provider = "google_maps"
organization.google_maps_api_key = "{encrypted_api_key}"
await db.commit()
```

2. **Identify Customers Needing Re-Geocoding**
```sql
SELECT COUNT(*)
FROM customers
WHERE organization_id = '{org_id}'
  AND geocoding_provider = 'openstreetmap';
```

3. **Re-Geocode with Google Maps (Background Job)**
```python
async def migrate_org_geocoding(org_id: UUID, db: AsyncSession):
    """Re-geocode all org customers using Google Maps."""

    # Get org and verify Google Maps configured
    org = await db.get(Organization, org_id)
    if org.default_map_provider != "google_maps":
        raise ValueError("Organization not configured for Google Maps")

    # Get all customers geocoded with OSM
    result = await db.execute(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.geocoding_provider == "openstreetmap"
        )
    )
    customers = result.scalars().all()

    logger.info(f"Re-geocoding {len(customers)} customers for org {org_id}")

    geocoding_service = GeocodingService(db)

    for customer in customers:
        try:
            await geocoding_service.geocode_customer_address(
                customer=customer,
                organization=org,
                force_re_geocode=True
            )
            logger.info(f"Re-geocoded customer {customer.id}")

        except Exception as e:
            logger.error(f"Failed to re-geocode customer {customer.id}: {e}")

    logger.info(f"Re-geocoding complete for org {org_id}")
```

**Run as Celery task (non-blocking):**
```python
@celery.task
def migrate_org_geocoding_task(org_id: str):
    asyncio.run(migrate_org_geocoding(UUID(org_id), get_async_session()))
```

### Scenario 2: Compare Provider Accuracy

**Use Case:** A/B test to verify Google Maps accuracy before migration.

**Implementation:**

```python
async def compare_geocoding_providers(address: str) -> dict:
    """Geocode address with both providers and compare results."""

    osm_provider = OpenStreetMapProvider()
    google_provider = GoogleMapsProvider(api_key=os.getenv("GOOGLE_MAPS_API_KEY"))

    osm_result = await osm_provider.geocode(address)
    google_result = await google_provider.geocode(address)

    return {
        "address": address,
        "openstreetmap": {
            "coordinates": (osm_result.latitude, osm_result.longitude) if osm_result else None,
            "formatted_address": osm_result.formatted_address if osm_result else None,
            "confidence": osm_result.confidence if osm_result else None,
        },
        "google_maps": {
            "coordinates": (google_result.latitude, google_result.longitude) if google_result else None,
            "formatted_address": google_result.formatted_address if google_result else None,
            "confidence": google_result.confidence if google_result else None,
        },
        "distance_diff_meters": calculate_distance(osm_result, google_result) if osm_result and google_result else None
    }
```

---

## Cost Analysis

### OpenStreetMap (Nominatim)

| Factor | Value |
|--------|-------|
| **Cost** | Free (with attribution) |
| **Rate Limit** | 1 request/second (strictly enforced) |
| **Accuracy** | Good for residential, less reliable for commercial |
| **Batch Import Speed** | Slow (100 addresses = 100 seconds minimum) |
| **Support** | Community (no SLA) |
| **Uptime** | ~99% (no guarantee) |

**Best For:** Starter tier, low-volume usage, development/testing

### Google Maps Platform

| Factor | Value |
|--------|-------|
| **Cost** | $5 per 1000 requests |
| **Free Tier** | $200/month credit = 40,000 free requests/month |
| **Rate Limit** | No strict limit (pay-per-use), 50 req/sec recommended |
| **Accuracy** | Superior for commercial addresses, structured data |
| **Batch Import Speed** | Fast (100 addresses = ~2 seconds with parallelization) |
| **Support** | Google Cloud support (with paid plan) |
| **Uptime** | 99.9% SLA |

**Best For:** Professional/Enterprise tiers, high-volume, production use

### Cost Comparison Example

**Scenario:** Organization with 500 customers, geocodes 50 new customers/month

| Provider | Cost/Month | Notes |
|----------|------------|-------|
| OpenStreetMap | $0 | Free, but slow (50 addresses = 50+ seconds) |
| Google Maps | $0.25 | 50 requests × $0.005 (well under $200 free tier) |

**Conclusion:** For most organizations, Google Maps is effectively free (under free tier limit) with superior accuracy and speed.

---

## API Key Management

### Security Best Practices

1. **Encrypt API Keys at Rest**
```python
# app/services/encryption.py
from cryptography.fernet import Fernet
import os

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # Store in environment
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_api_key(api_key: str) -> str:
    """Encrypt API key before storing in database."""
    return cipher.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key when retrieving from database."""
    return cipher.decrypt(encrypted_key.encode()).decode()
```

2. **Never Log API Keys**
```python
# ❌ BAD
logger.info(f"Using Google Maps API key: {api_key}")

# ✅ GOOD
logger.info(f"Using Google Maps API key: {api_key[:8]}...")
```

3. **Restrict API Key Scope (Google Cloud Console)**
- Enable only Geocoding API (not Maps JavaScript API, Places API, etc.)
- Set HTTP referrer restrictions (if applicable)
- Set IP address restrictions for server-side keys
- Rotate keys quarterly

4. **Monitor Usage**
```python
# Track Google Maps API usage per org
await UsageTracker.track(db, org_id, "geocoding_requests", metadata={"provider": "google_maps"})
```

### Enterprise: "Bring Your Own API Key"

**Use Case:** Large customer wants to use their own Google Maps billing account.

**Implementation:**

```python
# Organization can provide their own API key
organization.google_maps_api_key = encrypt_api_key(customer_provided_key)
organization.default_map_provider = "google_maps"
await db.commit()

# Factory will use their key
provider = GeocodingFactory.get_provider(organization)  # Uses customer's key
```

**Benefits:**
- Customer controls costs
- Customer gets Google Maps invoice directly
- We don't pay for their usage

---

## Summary

### Abstraction Layer Benefits

✅ **Flexibility:** Switch providers per organization
✅ **Cost Optimization:** Free tier for small orgs, Google for premium
✅ **Accuracy:** Google Maps for commercial addresses
✅ **Speed:** Parallel geocoding with Google (vs. 1 req/sec OSM)
✅ **Caching:** Reduce duplicate API calls
✅ **Metadata:** Track provider, user, timestamp for audit trail
✅ **Future-Proof:** Easy to add Mapbox, Azure Maps, etc.

### Implementation Checklist

**Phase 1: Abstraction Layer** (Current Phase)
- [ ] Create `app/services/geocoding/` directory
- [ ] Implement `interface.py` (GeocodingProvider ABC)
- [ ] Implement `openstreetmap.py` (existing provider)
- [ ] Implement `google_maps.py` (future provider)
- [ ] Implement `factory.py` (provider selection)
- [ ] Implement `exceptions.py`

**Phase 2: Database Changes**
- [ ] Add geocoding metadata fields to customers/drivers tables
- [ ] Create geocoding_cache table
- [ ] Migrate: mark existing geocoded addresses as "openstreetmap"

**Phase 3: Service Layer**
- [ ] Refactor `app/services/geocoding.py` to use factory
- [ ] Implement caching logic
- [ ] Add metadata tracking

**Phase 4: Testing**
- [ ] Unit tests for each provider
- [ ] Integration tests with real API calls (small dataset)
- [ ] Test provider switching
- [ ] Test cache hit/miss scenarios

**Phase 5: Production Rollout**
- [ ] Deploy abstraction layer (still using OSM)
- [ ] Monitor for regressions
- [ ] Enable Google Maps for demo organization
- [ ] A/B test accuracy comparison

**Phase 6: Enterprise Features** (Future)
- [ ] "Bring your own API key" for Enterprise tier
- [ ] Multi-provider fallback (try Google, fall back to OSM)
- [ ] Geocoding analytics dashboard

---

**Next Steps:**
1. Review this strategy with team
2. Confirm Google Maps Platform account setup
3. Implement Phase 1 (abstraction layer) during Phase 2 of SaaS Foundation
4. Test with demo organization before broader rollout
