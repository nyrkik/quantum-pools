"""
Customer management API endpoints.
Provides CRUD operations for pool service customers.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models.customer import Customer
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse
)
from app.services.geocoding import geocoding_service

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.post(
    "/",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer"
)
async def create_customer(
    customer: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new customer with the provided information.

    - **name**: Business name (for commercial, required)
    - **first_name**: First name (for residential)
    - **last_name**: Last name (for residential)
    - **display_name**: Display name (auto-generated if not provided)
    - **address**: Street address (required)
    - **service_type**: residential or commercial (required)
    - **difficulty**: 1-5 difficulty level (default: 1)
    - **service_day**: Day of week for service (required)
    - **locked**: Whether customer can be moved to different day (default: false)
    - **time_window_start**: Earliest service time (optional)
    - **time_window_end**: Latest service time (optional)
    """
    customer_data = customer.model_dump()

    # Auto-generate display_name if not provided
    if not customer_data.get('display_name'):
        if customer_data['service_type'] == 'residential':
            # For residential: "Last, First"
            last = customer_data.get('last_name', '')
            first = customer_data.get('first_name', '')
            customer_data['display_name'] = f"{last}, {first}".strip(', ')
        else:
            # For commercial: use name
            customer_data['display_name'] = customer_data.get('name', 'Unnamed')

    db_customer = Customer(**customer_data)

    # Geocode address to lat/lng
    coordinates = await geocoding_service.geocode_address(db_customer.address)
    if coordinates:
        db_customer.latitude, db_customer.longitude = coordinates

    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)
    return db_customer


@router.get(
    "/",
    response_model=CustomerListResponse,
    summary="List all customers with pagination"
)
async def list_customers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=5000, description="Items per page"),
    service_day: Optional[str] = Query(None, description="Filter by service day"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a paginated list of customers with optional filters.

    Filters:
    - **service_day**: Filter by specific day of week (includes multi-day schedules)
    - **service_type**: Filter by residential or commercial
    - **is_active**: Filter by active/inactive status
    """
    # Build base query with eager loading of assigned_driver
    query = select(Customer).options(selectinload(Customer.assigned_driver))

    # Apply filters
    if service_day:
        # Map day name to abbreviation for schedule checking
        day_abbrev_map = {
            'monday': 'Mo',
            'tuesday': 'Tu',
            'wednesday': 'We',
            'thursday': 'Th',
            'friday': 'Fr',
            'saturday': 'Sa',
            'sunday': 'Su'
        }
        day_lower = service_day.lower()
        day_abbrev = day_abbrev_map.get(day_lower)

        # Filter by either:
        # 1. Primary service_day matches (for single-day customers)
        # 2. Day abbreviation is in service_schedule (for multi-day customers)
        if day_abbrev:
            query = query.where(
                or_(
                    Customer.service_day == day_lower,
                    Customer.service_schedule.like(f'%{day_abbrev}%')
                )
            )
        else:
            query = query.where(Customer.service_day == day_lower)

    if service_type:
        query = query.where(Customer.service_type == service_type.lower())
    if is_active is not None:
        query = query.where(Customer.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Customer.name)

    # Execute query
    result = await db.execute(query)
    customers = result.scalars().all()

    return CustomerListResponse(
        customers=customers,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get(
    "/management-companies",
    response_model=list[str],
    summary="Get all management companies"
)
async def get_management_companies(
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a list of distinct management company names from existing customers.

    Returns an empty list if no management companies exist.
    """
    result = await db.execute(
        select(Customer.management_company)
        .where(Customer.management_company.isnot(None))
        .where(Customer.management_company != '')
        .distinct()
        .order_by(Customer.management_company)
    )
    companies = result.scalars().all()
    return companies


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get a specific customer"
)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific customer by ID.
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} not found"
        )

    return customer


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update a customer"
)
async def update_customer_put(
    customer_id: UUID,
    customer_update: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing customer's information (PUT method).

    Only provided fields will be updated. All fields are optional.
    """
    return await update_customer(customer_id, customer_update, db)


@router.patch(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update a customer (partial)"
)
async def update_customer_patch(
    customer_id: UUID,
    customer_update: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing customer's information (PATCH method).

    Only provided fields will be updated. All fields are optional.
    """
    return await update_customer(customer_id, customer_update, db)


async def update_customer(
    customer_id: UUID,
    customer_update: CustomerUpdate,
    db: AsyncSession
):
    """
    Shared update logic for both PUT and PATCH methods.

    Only provided fields will be updated. All fields are optional.
    """
    # Fetch existing customer
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} not found"
        )

    # Update fields
    update_data = customer_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)

    # Auto-generate display_name if name fields changed but display_name not explicitly provided
    name_fields_changed = any(f in update_data for f in ['name', 'first_name', 'last_name'])
    if name_fields_changed and 'display_name' not in update_data:
        if customer.service_type == 'residential':
            # For residential: "Last, First"
            last = customer.last_name or ''
            first = customer.first_name or ''
            customer.display_name = f"{last}, {first}".strip(', ')
        else:
            # For commercial: use name
            customer.display_name = customer.name or 'Unnamed'

    # Re-geocode if address changed (but not if latitude/longitude were explicitly provided)
    if "address" in update_data and "latitude" not in update_data and "longitude" not in update_data:
        coordinates = await geocoding_service.geocode_address(customer.address)
        if coordinates:
            customer.latitude, customer.longitude = coordinates

    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer"
)
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a customer by ID.

    This will also delete all associated route stops.
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} not found"
        )

    await db.delete(customer)
    await db.commit()


@router.get(
    "/service-day/{day}",
    response_model=list[CustomerResponse],
    summary="Get all customers for a specific service day"
)
async def get_customers_by_day(
    day: str,
    is_active: bool = Query(True, description="Filter by active status"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all customers scheduled for a specific day of the week.

    Includes both single-day customers and multi-day customers whose schedule
    includes this day. Useful for generating daily route plans.
    """
    # Map day name to abbreviation for schedule checking
    day_abbrev_map = {
        'monday': 'Mo',
        'tuesday': 'Tu',
        'wednesday': 'We',
        'thursday': 'Th',
        'friday': 'Fr',
        'saturday': 'Sa',
        'sunday': 'Su'
    }
    day_lower = day.lower()
    day_abbrev = day_abbrev_map.get(day_lower)

    # Build query with day filter
    query = select(Customer).where(Customer.is_active == is_active)

    if day_abbrev:
        query = query.where(
            or_(
                Customer.service_day == day_lower,
                Customer.service_schedule.like(f'%{day_abbrev}%')
            )
        )
    else:
        query = query.where(Customer.service_day == day_lower)

    query = query.order_by(Customer.name)

    result = await db.execute(query)
    customers = result.scalars().all()
    return customers
