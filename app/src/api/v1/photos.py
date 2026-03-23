"""Property photo endpoints — upload, gallery, hero management."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.photo_service import PhotoService

router = APIRouter(prefix="/photos", tags=["photos"])


class PropertyPhotoResponse(BaseModel):
    id: str
    property_id: str
    water_feature_id: Optional[str] = None
    filename: str
    url: str
    caption: Optional[str] = None
    is_hero: bool
    uploaded_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CaptionRequest(BaseModel):
    caption: Optional[str] = None


def _to_response(photo) -> PropertyPhotoResponse:
    return PropertyPhotoResponse(
        id=photo.id,
        property_id=photo.property_id,
        water_feature_id=photo.water_feature_id,
        filename=photo.filename,
        url=f"/uploads/photos/{photo.property_id}/{photo.filename}",
        caption=photo.caption,
        is_hero=photo.is_hero,
        uploaded_by=photo.uploaded_by,
        created_at=photo.created_at,
    )


@router.get("/heroes", response_model=dict[str, PropertyPhotoResponse])
async def get_hero_images(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PhotoService(db)
    heroes = await svc.get_heroes(ctx.organization_id)
    return {prop_id: _to_response(photo) for prop_id, photo in heroes.items()}


@router.get("/properties/{property_id}", response_model=list[PropertyPhotoResponse])
async def list_photos(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PhotoService(db)
    photos = await svc.list_photos(ctx.organization_id, property_id)
    return [_to_response(p) for p in photos]


@router.post("/properties/{property_id}/upload", response_model=PropertyPhotoResponse)
async def upload_photo(
    property_id: str,
    photo: UploadFile = File(...),
    water_feature_id: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    file_bytes = await photo.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    svc = PhotoService(db)
    try:
        result = await svc.upload_photo(
            ctx.organization_id, property_id,
            file_bytes, photo.filename or "photo.jpg",
            wf_id=water_feature_id, caption=caption,
            uploaded_by=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_response(result)


@router.put("/{photo_id}/hero", response_model=PropertyPhotoResponse)
async def set_hero(
    photo_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from src.models.property_photo import PropertyPhoto
    result = await db.execute(
        select(PropertyPhoto).where(
            PropertyPhoto.id == photo_id,
            PropertyPhoto.organization_id == ctx.organization_id,
        )
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    svc = PhotoService(db)
    updated = await svc.set_hero(ctx.organization_id, photo.property_id, photo_id)
    return _to_response(updated)


@router.put("/{photo_id}/caption", response_model=PropertyPhotoResponse)
async def update_caption(
    photo_id: str,
    body: CaptionRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PhotoService(db)
    try:
        updated = await svc.update_caption(ctx.organization_id, photo_id, body.caption)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_response(updated)


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from src.models.property_photo import PropertyPhoto
    result = await db.execute(
        select(PropertyPhoto).where(
            PropertyPhoto.id == photo_id,
            PropertyPhoto.organization_id == ctx.organization_id,
        )
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    svc = PhotoService(db)
    await svc.delete_photo(ctx.organization_id, photo.property_id, photo_id)
