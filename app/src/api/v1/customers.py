"""Customer endpoints — all org-scoped."""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy import select, func
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
        resp.wf_summary = await svc.get_property_wf_summary(c.id)
        results.append(resp)
    return {"items": results, "total": total}


@router.get("/companies", response_model=list[str])
async def list_companies(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.models.customer import Customer
    stmt = (
        select(Customer.company_name)
        .where(Customer.organization_id == ctx.organization_id, Customer.company_name.isnot(None), Customer.company_name != "")
        .distinct()
        .order_by(Customer.company_name)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


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
    # Split into customer, property, and WF fields
    property_fields = {k: data.pop(k) for k in ["address", "city", "state", "zip_code", "gate_code", "access_instructions", "dog_on_property"]}
    wf_fields = {k: data.pop(k) for k in ["water_type", "pool_type"]}
    # Assign customer rate to the first WF
    if data.get("monthly_rate"):
        wf_fields["monthly_rate"] = data["monthly_rate"]
    # Set billing address from service address if not provided
    if not data.get("billing_address"):
        data["billing_address"] = property_fields["address"]
        data["billing_city"] = property_fields["city"]
        data["billing_state"] = property_fields["state"]
        data["billing_zip"] = property_fields["zip_code"]
    customer, prop = await svc.create_with_property(
        ctx.organization_id, data, property_fields, wf_fields,
    )
    # Sync property rate from WF, customer rate from property
    from src.services.rate_sync import sync_rates_for_property
    await sync_rates_for_property(db, prop.id)
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
    background_tasks: BackgroundTasks,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    customer = await svc.update(ctx.organization_id, customer_id, **body.model_dump(exclude_unset=True))
    # Re-run EMD match when status changes (active/inactive affects matching)
    if body.status is not None or body.is_active is not None:
        background_tasks.add_task(_emd_auto_match, ctx.organization_id)
    return CustomerResponse.model_validate(customer)


async def _emd_auto_match(organization_id: str):
    """Background task to auto-match EMD facilities after customer status changes."""
    try:
        async with get_db_context() as db:
            from src.services.emd.service import EMDService
            svc = EMDService(db)
            await svc.auto_match_facilities(organization_id)
    except Exception:
        pass


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CustomerService(db)
    await svc.delete(ctx.organization_id, customer_id)
