"""Charge templates CRUD — predefined surcharge types per org."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.charge_service import ChargeService

router = APIRouter(prefix="/charge-templates", tags=["charge-templates"])


class TemplateCreate(BaseModel):
    name: str
    default_amount: float
    category: str = "other"
    is_taxable: bool = True
    requires_approval: bool = False
    sort_order: int = 0


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    default_amount: Optional[float] = None
    category: Optional[str] = None
    is_taxable: Optional[bool] = None
    requires_approval: Optional[bool] = None
    sort_order: Optional[int] = None


@router.get("")
async def list_templates(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    return await svc.list_templates(ctx.organization_id)


@router.post("")
async def create_template(
    body: TemplateCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    return await svc.create_template(ctx.organization_id, **body.model_dump())


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    try:
        return await svc.update_template(
            ctx.organization_id, template_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    deleted = await svc.delete_template(ctx.organization_id, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
