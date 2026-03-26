"""Vendor CRUD — org-configurable supplier list."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.vendor_service import VendorService

router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    name: str
    provider_type: str = "generic"
    portal_url: Optional[str] = None
    search_url_template: Optional[str] = None
    account_number: Optional[str] = None
    sort_order: int = 0


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    portal_url: Optional[str] = None
    search_url_template: Optional[str] = None
    account_number: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


@router.get("")
async def list_vendors(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VendorService(db)
    return await svc.list_vendors(ctx.organization_id)


@router.post("")
async def create_vendor(
    body: VendorCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = VendorService(db)
    return await svc.create_vendor(ctx.organization_id, **body.model_dump())


@router.put("/{vendor_id}")
async def update_vendor(
    vendor_id: str,
    body: VendorUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = VendorService(db)
    try:
        return await svc.update_vendor(
            ctx.organization_id, vendor_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{vendor_id}", status_code=204)
async def delete_vendor(
    vendor_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = VendorService(db)
    deleted = await svc.delete_vendor(ctx.organization_id, vendor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Vendor not found")


@router.get("/{vendor_id}/search-url")
async def get_search_url(
    vendor_id: str,
    q: str = Query(..., min_length=1),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = VendorService(db)
    url = await svc.get_search_url(ctx.organization_id, vendor_id, q)
    if not url:
        raise HTTPException(status_code=404, detail="Vendor not found or no search template")
    return {"url": url}


@router.post("/seed-defaults")
async def seed_defaults(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = VendorService(db)
    return await svc.seed_defaults(ctx.organization_id)
