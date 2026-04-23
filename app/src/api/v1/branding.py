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
    auto_signature_prefix: Optional[bool] = None
    include_logo_in_signature: Optional[bool] = None
    allow_per_user_signature: Optional[bool] = None
    website_url: Optional[str] = None


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
        "website_url": org.website_url,
        "email_signature": org.agent_signature,
        "auto_signature_prefix": bool(org.auto_signature_prefix),
        "include_logo_in_signature": bool(org.include_logo_in_signature),
        "allow_per_user_signature": bool(org.allow_per_user_signature),
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
    if body.auto_signature_prefix is not None:
        org.auto_signature_prefix = bool(body.auto_signature_prefix)
    if body.include_logo_in_signature is not None:
        org.include_logo_in_signature = bool(body.include_logo_in_signature)
    if body.allow_per_user_signature is not None:
        org.allow_per_user_signature = bool(body.allow_per_user_signature)
    if body.website_url is not None:
        org.website_url = body.website_url.strip() or None

    await db.commit()
    return {
        "name": org.name,
        "logo_url": org.logo_url,
        "primary_color": org.primary_color,
        "tagline": org.tagline,
        "website_url": org.website_url,
        "email_signature": org.agent_signature,
        "auto_signature_prefix": bool(org.auto_signature_prefix),
        "include_logo_in_signature": bool(org.include_logo_in_signature),
        "allow_per_user_signature": bool(org.allow_per_user_signature),
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


# ── Organization Addresses ────────────────────────────────────────────

import json


@router.get("/addresses")
async def get_addresses(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    org = (await db.execute(select(Organization).where(Organization.id == ctx.organization_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    addresses = json.loads(org.addresses or "{}") if org.addresses else {}
    return {"addresses": addresses}


class AddressesUpdate(BaseModel):
    addresses: dict  # {mailing: {street, city, state, zip}, physical: {same_as: "mailing"} | {street...}, ...}


@router.put("/addresses")
async def update_addresses(
    body: AddressesUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    org = (await db.execute(select(Organization).where(Organization.id == ctx.organization_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Validate structure
    valid_keys = {"mailing", "physical", "billing"}
    valid_fields = {"street", "city", "state", "zip", "same_as"}
    for key, val in body.addresses.items():
        if key not in valid_keys:
            raise HTTPException(status_code=400, detail=f"Invalid address type: {key}")
        if not isinstance(val, dict):
            raise HTTPException(status_code=400, detail=f"Address '{key}' must be an object")
        if "same_as" in val:
            if val["same_as"] not in valid_keys or val["same_as"] == key:
                raise HTTPException(status_code=400, detail=f"Invalid same_as reference for '{key}'")
        else:
            for field in val:
                if field not in valid_fields:
                    raise HTTPException(status_code=400, detail=f"Invalid field '{field}' in '{key}'")

    org.addresses = json.dumps(body.addresses)

    # Also sync flat fields from mailing for backward compat
    mailing = body.addresses.get("mailing", {})
    if mailing and "same_as" not in mailing:
        org.address = mailing.get("street") or org.address
        org.city = mailing.get("city") or org.city
        org.state = mailing.get("state") or org.state
        org.zip_code = mailing.get("zip") or org.zip_code

    await db.commit()
    return {"addresses": body.addresses}
