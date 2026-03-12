"""Batch geocode all properties missing lat/lng."""

import asyncio
import sys
import os

# Add app dir to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.models.property import Property
from src.models.geocode_cache import GeocodeCache
from src.services.geocoding_service import GeocodingService


async def main():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(
            select(Property).where(Property.lat.is_(None), Property.is_active == True)
        )
        properties = result.scalars().all()
        print(f"Found {len(properties)} properties to geocode")

        svc = GeocodingService(db)
        success, failed = 0, 0

        for prop in properties:
            full_addr = f"{prop.address}, {prop.city}, {prop.state} {prop.zip_code}"
            try:
                result = await svc.geocode(full_addr)
                if result:
                    lat, lng, provider = result
                    prop.lat = lat
                    prop.lng = lng
                    prop.geocode_provider = provider
                    success += 1
                    print(f"  OK  {full_addr} -> {lat:.6f}, {lng:.6f} ({provider})")
                else:
                    failed += 1
                    print(f"  FAIL {full_addr} -> no result")
            except Exception as e:
                failed += 1
                print(f"  ERR  {full_addr} -> {e}")

            # OSM rate limit: 1 req/sec
            await asyncio.sleep(1.1)

        await db.commit()
        print(f"\nDone: {success} geocoded, {failed} failed")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
