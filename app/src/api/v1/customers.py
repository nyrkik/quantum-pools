"""Customer endpoints — all org-scoped."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import NotFoundError
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from src.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=dict)
async def list_customers(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    customers, total = await svc.list(ctx.organization_id, search=search, is_active=is_active, skip=skip, limit=limit)
    results = []
    for c in customers:
        resp = CustomerResponse.model_validate(c)
        resp.property_count = await svc.get_property_count(c.id)
        results.append(resp)
    return {"items": results, "total": total}


@router.post("", response_model=CustomerResponse, status_code=201)
async def create_customer(
    body: CustomerCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    customer = await svc.create(ctx.organization_id, **body.model_dump())
    return CustomerResponse.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    customer = await svc.get(ctx.organization_id, customer_id)
    resp = CustomerResponse.model_validate(customer)
    resp.property_count = await svc.get_property_count(customer.id)
    return resp


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    customer = await svc.update(ctx.organization_id, customer_id, **body.model_dump(exclude_unset=True))
    return CustomerResponse.model_validate(customer)


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    await svc.delete(ctx.organization_id, customer_id)
