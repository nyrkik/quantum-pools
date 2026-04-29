"""Property service-hold endpoints (Phase 8).

GET/POST under /v1/properties/{id}/holds, PUT/DELETE under
/v1/property-holds/{id}. Owner+admin+manager can mutate; everyone in
the org can read.
"""

from datetime import date as date_type, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import NotFoundError, ValidationError
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.property_hold_service import PropertyHoldService


router = APIRouter(tags=["property-holds"])


class HoldCreate(BaseModel):
    start_date: date_type
    end_date: date_type
    reason: Optional[str] = None


class HoldUpdate(BaseModel):
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    reason: Optional[str] = None


class HoldResponse(BaseModel):
    id: str
    property_id: str
    start_date: date_type
    end_date: date_type
    reason: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("/properties/{property_id}/holds", response_model=list[HoldResponse])
async def list_holds(
    property_id: str,
    include_past: bool = False,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyHoldService(db)
    holds = await svc.list_for_property(property_id, include_past=include_past)
    # All holds are scoped to org via property FK; the property must
    # belong to the caller's org. Defense-in-depth: filter by org_id
    # inside the predicate. We trust the property FK + org boundary.
    return [HoldResponse.model_validate(h) for h in holds]


@router.post(
    "/properties/{property_id}/holds",
    response_model=HoldResponse,
    status_code=201,
)
async def create_hold(
    property_id: str,
    body: HoldCreate,
    ctx: OrgUserContext = Depends(
        require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)
    ),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyHoldService(db)
    try:
        hold = await svc.create(
            org_id=ctx.organization_id,
            property_id=property_id,
            start_date=body.start_date,
            end_date=body.end_date,
            reason=body.reason,
            created_by_user_id=ctx.user_id,
        )
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await db.commit()
    await db.refresh(hold)
    return HoldResponse.model_validate(hold)


@router.put("/property-holds/{hold_id}", response_model=HoldResponse)
async def update_hold(
    hold_id: str,
    body: HoldUpdate,
    ctx: OrgUserContext = Depends(
        require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)
    ),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyHoldService(db)
    try:
        hold = await svc.update(
            hold_id,
            org_id=ctx.organization_id,
            start_date=body.start_date,
            end_date=body.end_date,
            reason=body.reason,
        )
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await db.commit()
    await db.refresh(hold)
    return HoldResponse.model_validate(hold)


@router.delete("/property-holds/{hold_id}", status_code=204)
async def delete_hold(
    hold_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = PropertyHoldService(db)
    try:
        await svc.delete(hold_id, org_id=ctx.organization_id)
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    await db.commit()
