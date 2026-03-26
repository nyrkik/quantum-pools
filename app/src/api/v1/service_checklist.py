"""Service checklist settings — org-configurable checklist items for visits."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.models.service_checklist_item import ServiceChecklistItem

router = APIRouter(prefix="/service-checklist", tags=["service-checklist"])


class ChecklistItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str = "cleaning"
    sort_order: int = 0
    applies_to: str = "all"
    is_default: bool = True


class ChecklistItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = None
    sort_order: Optional[int] = None
    applies_to: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class ChecklistItemResponse(BaseModel):
    id: str
    name: str
    category: str
    sort_order: int
    applies_to: str
    is_default: bool
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ChecklistItemResponse])
async def list_checklist_items(
    include_inactive: bool = False,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List org checklist items."""
    query = select(ServiceChecklistItem).where(
        ServiceChecklistItem.organization_id == ctx.organization_id
    )
    if not include_inactive:
        query = query.where(ServiceChecklistItem.is_active == True)
    query = query.order_by(ServiceChecklistItem.sort_order, ServiceChecklistItem.name)

    result = await db.execute(query)
    return [ChecklistItemResponse.model_validate(item) for item in result.scalars().all()]


@router.post("", response_model=ChecklistItemResponse, status_code=201)
async def create_checklist_item(
    body: ChecklistItemCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new checklist item."""
    item = ServiceChecklistItem(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        **body.model_dump(),
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return ChecklistItemResponse.model_validate(item)


@router.put("/{item_id}", response_model=ChecklistItemResponse)
async def update_checklist_item(
    item_id: str,
    body: ChecklistItemUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Update a checklist item."""
    result = await db.execute(
        select(ServiceChecklistItem).where(
            ServiceChecklistItem.id == item_id,
            ServiceChecklistItem.organization_id == ctx.organization_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)

    await db.flush()
    await db.refresh(item)
    return ChecklistItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(
    item_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a checklist item (set is_active=False)."""
    result = await db.execute(
        select(ServiceChecklistItem).where(
            ServiceChecklistItem.id == item_id,
            ServiceChecklistItem.organization_id == ctx.organization_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    item.is_active = False
    await db.flush()
