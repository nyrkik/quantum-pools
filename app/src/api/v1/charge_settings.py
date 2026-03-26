"""Charge settings — threshold configuration for auto-approve, photo, etc."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from src.core.database import get_db
from src.api.deps import require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.charge_service import ChargeService

router = APIRouter(prefix="/charge-settings", tags=["charge-settings"])


class ThresholdUpdate(BaseModel):
    auto_approve_threshold: Optional[float] = None
    separate_invoice_threshold: Optional[float] = None
    require_photo_threshold: Optional[float] = None


@router.get("")
async def get_thresholds(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    return await svc.get_thresholds(ctx.organization_id)


@router.put("")
async def update_thresholds(
    body: ThresholdUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = ChargeService(db)
    try:
        return await svc.update_thresholds(
            ctx.organization_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
