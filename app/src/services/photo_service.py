"""Property photo service — upload, gallery, hero management."""

import uuid
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.exceptions import NotFoundError
from src.models.property_photo import PropertyPhoto
from src.models.property import Property

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "photos"
MAX_PHOTOS_PER_PROPERTY = 8

logger = logging.getLogger(__name__)


class PhotoService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_photos(self, organization_id: str, property_id: str) -> list[PropertyPhoto]:
        result = await self.db.execute(
            select(PropertyPhoto).where(
                PropertyPhoto.property_id == property_id,
                PropertyPhoto.organization_id == organization_id,
            ).order_by(PropertyPhoto.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_heroes(self, organization_id: str) -> dict[str, PropertyPhoto]:
        result = await self.db.execute(
            select(PropertyPhoto).where(
                PropertyPhoto.organization_id == organization_id,
                PropertyPhoto.is_hero == True,
            )
        )
        return {p.property_id: p for p in result.scalars().all()}

    async def upload_photo(
        self, organization_id: str, property_id: str,
        file_bytes: bytes, filename: str,
        bow_id: Optional[str] = None, caption: Optional[str] = None,
        uploaded_by: Optional[str] = None,
    ) -> PropertyPhoto:
        # Verify property exists
        result = await self.db.execute(
            select(Property).where(
                Property.id == property_id,
                Property.organization_id == organization_id,
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError(f"Property {property_id} not found")

        # Check limit
        existing = await self.list_photos(organization_id, property_id)
        if len(existing) >= MAX_PHOTOS_PER_PROPERTY:
            raise ValueError(f"Maximum {MAX_PHOTOS_PER_PROPERTY} photos per property")

        # Save file
        prop_dir = UPLOAD_DIR / property_id
        prop_dir.mkdir(parents=True, exist_ok=True)
        photo_id = str(uuid.uuid4())
        ext = Path(filename).suffix or ".jpg"
        safe_filename = f"{photo_id}{ext}"
        filepath = prop_dir / safe_filename
        filepath.write_bytes(file_bytes)

        # Auto-hero if first photo
        is_hero = len(existing) == 0

        photo = PropertyPhoto(
            id=photo_id,
            property_id=property_id,
            organization_id=organization_id,
            body_of_water_id=bow_id,
            filename=safe_filename,
            caption=caption,
            is_hero=is_hero,
            uploaded_by=uploaded_by,
        )
        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)
        return photo

    async def set_hero(
        self, organization_id: str, property_id: str, photo_id: str
    ) -> PropertyPhoto:
        photos = await self.list_photos(organization_id, property_id)
        target = None
        for p in photos:
            if p.id == photo_id:
                p.is_hero = True
                target = p
            else:
                p.is_hero = False
        if not target:
            raise NotFoundError(f"Photo {photo_id} not found")
        await self.db.flush()
        await self.db.refresh(target)
        return target

    async def update_caption(
        self, organization_id: str, photo_id: str, caption: Optional[str]
    ) -> PropertyPhoto:
        result = await self.db.execute(
            select(PropertyPhoto).where(
                PropertyPhoto.id == photo_id,
                PropertyPhoto.organization_id == organization_id,
            )
        )
        photo = result.scalar_one_or_none()
        if not photo:
            raise NotFoundError(f"Photo {photo_id} not found")
        photo.caption = caption
        await self.db.flush()
        await self.db.refresh(photo)
        return photo

    async def delete_photo(
        self, organization_id: str, property_id: str, photo_id: str
    ) -> None:
        result = await self.db.execute(
            select(PropertyPhoto).where(
                PropertyPhoto.id == photo_id,
                PropertyPhoto.property_id == property_id,
                PropertyPhoto.organization_id == organization_id,
            )
        )
        photo = result.scalar_one_or_none()
        if not photo:
            raise NotFoundError(f"Photo {photo_id} not found")

        was_hero = photo.is_hero

        filepath = UPLOAD_DIR / property_id / photo.filename
        if filepath.exists():
            filepath.unlink()

        await self.db.delete(photo)
        await self.db.flush()

        if was_hero:
            remaining = await self.list_photos(organization_id, property_id)
            if remaining:
                remaining[0].is_hero = True
                await self.db.flush()
