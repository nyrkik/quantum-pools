"""Branding endpoints — logo upload and theme settings."""

import os
import uuid
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.api.deps import require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.models.organization import Organization

router = APIRouter(prefix="/branding", tags=["branding"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "branding"
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
MAX_SIZE = 2 * 1024 * 1024  # 2MB


class BrandingUpdate(BaseModel):
    primary_color: Optional[str] = None
    tagline: Optional[str] = None
    organization_name: Optional[str] = None
    email_signature: Optional[str] = None


@router.get("")
async def get_branding(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == ctx.organization_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "name": org.name,
        "logo_url": org.logo_url,
        "primary_color": org.primary_color,
        "tagline": org.tagline,
        "email_signature": org.agent_signature,
    }


@router.put("")
async def update_branding(
    body: BrandingUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == ctx.organization_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if body.primary_color is not None:
        # Validate hex color
        color = body.primary_color.strip()
        if color and not (color.startswith("#") and len(color) in (4, 7) and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
            raise HTTPException(status_code=400, detail="Invalid hex color")
        org.primary_color = color or None
    if body.tagline is not None:
        org.tagline = body.tagline.strip() or None
    if body.organization_name is not None:
        name = body.organization_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Organization name is required")
        org.name = name
    if body.email_signature is not None:
        org.agent_signature = body.email_signature.strip() or None

    await db.commit()
    return {
        "name": org.name,
        "logo_url": org.logo_url,
        "primary_color": org.primary_color,
        "tagline": org.tagline,
        "email_signature": org.agent_signature,
    }


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use PNG, JPEG, SVG, or WebP.")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum 2MB.")

    # Save file
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "png"
    filename = f"{ctx.organization_id}-logo.{ext}"
    filepath = UPLOAD_DIR / filename

    with open(filepath, "wb") as f:
        f.write(content)

    # Update org
    logo_url = f"/uploads/branding/{filename}"
    result = await db.execute(select(Organization).where(Organization.id == ctx.organization_id))
    org = result.scalar_one_or_none()
    if org:
        org.logo_url = logo_url
        await db.commit()

    return {"logo_url": logo_url}
