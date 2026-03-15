"""Customer endpoints — all org-scoped."""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db, get_db_context
from src.core.exceptions import NotFoundError
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse, CustomerCreateWithProperty
from src.services.customer_service import CustomerService
from src.services.geocoding_service import GeocodingService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=dict)
async def list_customers(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    status: Optional[List[str]] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    customers, total = await svc.list(ctx.organization_id, search=search, is_active=is_active, status=status, skip=skip, limit=limit)
    results = []
    for c in customers:
        resp = CustomerResponse.model_validate(c)
        resp.property_count = await svc.get_property_count(c.id)
        first_prop = await svc.get_first_property(c.id)
        resp.first_property_id = first_prop.id if first_prop else None
        resp.first_property_address = first_prop.address if first_prop else None
        resp.first_property_pool_type = await svc.get_first_property_pool_type(c.id)
        resp.bow_summary = await svc.get_property_bow_summary(c.id)
        results.append(resp)
    return {"items": results, "total": total}


async def _geocode_property(property_id: str, address: str):
    """Background task to geocode a property."""
    from src.services.property_service import PropertyService
    async with get_db_context() as db:
        geo_svc = GeocodingService(db)
        result = await geo_svc.geocode(address)
        if result:
            prop_svc = PropertyService(db)
            await prop_svc.update_geocode(property_id, result[0], result[1], result[2])


@router.post("/with-property", response_model=CustomerResponse, status_code=201)
async def create_customer_with_property(
    body: CustomerCreateWithProperty,
    background_tasks: BackgroundTasks,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    data = body.model_dump()
    # Split into customer, property, and BOW fields
    property_fields = {k: data.pop(k) for k in ["address", "city", "state", "zip_code", "gate_code", "access_instructions", "dog_on_property"]}
    bow_fields = {k: data.pop(k) for k in ["water_type", "pool_type"]}
    # Set billing address from service address if not provided
    if not data.get("billing_address"):
        data["billing_address"] = property_fields["address"]
        data["billing_city"] = property_fields["city"]
        data["billing_state"] = property_fields["state"]
        data["billing_zip"] = property_fields["zip_code"]
    customer, prop = await svc.create_with_property(
        ctx.organization_id, data, property_fields, bow_fields,
    )
    full_addr = f"{prop.address}, {prop.city}, {prop.state} {prop.zip_code}"
    background_tasks.add_task(_geocode_property, prop.id, full_addr)
    resp = CustomerResponse.model_validate(customer)
    resp.property_count = 1
    resp.first_property_address = prop.address
    return resp


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
