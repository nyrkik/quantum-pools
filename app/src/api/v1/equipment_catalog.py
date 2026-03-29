"""Equipment Catalog — canonical equipment reference with AI resolution."""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext, require_roles
from src.models.organization_user import OrgRole
from src.services.parts.equipment_catalog_service import EquipmentCatalogService

router = APIRouter(prefix="/equipment-catalog", tags=["equipment-catalog"])


class CatalogEntryResponse(BaseModel):
    id: str
    canonical_name: str
    equipment_type: str
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    category: Optional[str] = None
    specs: Optional[dict] = None
    aliases: list = []
    is_common: bool = False
    source: str = "manual"


class CatalogCreateRequest(BaseModel):
    canonical_name: str
    equipment_type: str = "equipment"
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    category: Optional[str] = None
    specs: Optional[dict] = None
    aliases: list = []


class ResolveRequest(BaseModel):
    raw_text: str
    equipment_type: str = "equipment"


@router.get("/search", response_model=List[CatalogEntryResponse])
async def search_catalog(
    q: str = Query("", min_length=0),
    type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = EquipmentCatalogService(db)
    return await svc.search(q, equipment_type=type, limit=limit)


@router.get("/{catalog_id}")
async def get_catalog_entry(
    catalog_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = EquipmentCatalogService(db)
    entry = await svc.get_by_id(catalog_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    return entry


@router.post("", response_model=CatalogEntryResponse, status_code=201)
async def create_catalog_entry(
    body: CatalogCreateRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = EquipmentCatalogService(db)
    entry = await svc.create(body.model_dump(), org_id=ctx.organization_id)
    return EquipmentCatalogService._to_dict(entry)


@router.put("/{catalog_id}", response_model=CatalogEntryResponse)
async def update_catalog_entry(
    catalog_id: str,
    body: CatalogCreateRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = EquipmentCatalogService(db)
    entry = await svc.update(catalog_id, body.model_dump(exclude_unset=True))
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    return EquipmentCatalogService._to_dict(entry)


@router.post("/resolve")
async def resolve_equipment(
    body: ResolveRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve raw equipment text to a canonical catalog entry.
    Searches existing entries first, then uses AI to parse and create if needed.
    """
    svc = EquipmentCatalogService(db)
    return await svc.resolve(body.raw_text, body.equipment_type)
