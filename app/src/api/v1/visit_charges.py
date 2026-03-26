"""Visit charges — tech field charges + approval workflow."""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from src.core.database import get_db
from src.core.config import get_settings
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.charge_service import ChargeService

router = APIRouter(prefix="/visit-charges", tags=["visit-charges"])


class ChargeCreate(BaseModel):
    property_id: str
    customer_id: str
    visit_id: Optional[str] = None
    template_id: Optional[str] = None
    description: str
    amount: float
    category: str = "other"
    is_taxable: bool = True
    notes: Optional[str] = None


class ChargeUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    is_taxable: Optional[bool] = None
    notes: Optional[str] = None


class RejectBody(BaseModel):
    reason: str


@router.post("")
async def create_charge(
    body: ChargeCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a visit charge. Any authenticated user (technician+) can create."""
    svc = ChargeService(db)
    return await svc.create_charge(
        ctx.organization_id,
        ctx.user.id,
        **body.model_dump(),
    )


@router.get("")
async def list_charges(
    status: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    return await svc.list_charges(
        ctx.organization_id,
        status=status,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/pending")
async def pending_count(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    count = await svc.get_pending_count(ctx.organization_id)
    return {"pending": count}


@router.get("/uninvoiced")
async def uninvoiced_charges(
    customer_id: str = Query(...),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    return await svc.get_uninvoiced(ctx.organization_id, customer_id)


@router.put("/{charge_id}")
async def update_charge(
    charge_id: str,
    body: ChargeUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    # Verify charge exists and check ownership
    charge = await svc.get_charge(ctx.organization_id, charge_id)
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")
    # Only creator or admin+ can update
    if charge["created_by"] != ctx.user.id and ctx.role not in (OrgRole.owner, OrgRole.admin):
        raise HTTPException(status_code=403, detail="Not authorized to update this charge")
    try:
        return await svc.update_charge(
            ctx.organization_id, charge_id, ctx.user.id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{charge_id}/approve")
async def approve_charge(
    charge_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    try:
        return await svc.approve_charge(ctx.organization_id, charge_id, ctx.user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{charge_id}/reject")
async def reject_charge(
    charge_id: str,
    body: RejectBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    try:
        return await svc.reject_charge(ctx.organization_id, charge_id, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{charge_id}/photo")
async def upload_charge_photo(
    charge_id: str,
    photo: UploadFile = File(...),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload evidence photo for a charge. Creator only."""
    svc = ChargeService(db)
    charge = await svc.get_charge(ctx.organization_id, charge_id)
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")
    if charge["created_by"] != ctx.user.id and ctx.role not in (OrgRole.owner, OrgRole.admin):
        raise HTTPException(status_code=403, detail="Not authorized")

    # Validate MIME
    allowed = ("image/jpeg", "image/png", "image/webp")
    if not photo.content_type or photo.content_type not in allowed:
        raise HTTPException(status_code=400, detail="File must be JPEG, PNG, or WebP")

    file_bytes = await photo.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Save to disk
    settings = get_settings()
    upload_dir = os.path.join(settings.upload_dir, "charges", charge["property_id"])
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(photo.filename or "photo.jpg")[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, "wb") as f:
        f.write(file_bytes)

    photo_url = f"/uploads/charges/{charge['property_id']}/{filename}"
    return await svc.set_photo_url(ctx.organization_id, charge_id, photo_url)
