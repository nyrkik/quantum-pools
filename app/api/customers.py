"""
Customer management API endpoints.
Provides CRUD operations for pool service customers.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
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

    - **name**: Customer name (required)
    - **address**: Street address (required)
    - **service_type**: residential or commercial (required)
    - **difficulty**: 1-5 difficulty level (default: 1)
    - **service_day**: Day of week for service (required)
    - **locked**: Whether customer can be moved to different day (default: false)
    - **time_window_start**: Earliest service time (optional)
    - **time_window_end**: Latest service time (optional)
    """
    db_customer = Customer(**customer.model_dump())

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
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    service_day: Optional[str] = Query(None, description="Filter by service day"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a paginated list of customers with optional filters.

    Filters:
    - **service_day**: Filter by specific day of week
    - **service_type**: Filter by residential or commercial
    - **is_active**: Filter by active/inactive status
    """
    # Build base query
    query = select(Customer)

    # Apply filters
    if service_day:
        query = query.where(Customer.service_day == service_day.lower())
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
async def update_customer(
    customer_id: UUID,
    customer_update: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing customer's information.

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

    # Re-geocode if address changed
    if "address" in update_data:
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

    Useful for generating daily route plans.
    """
    result = await db.execute(
        select(Customer)
        .where(Customer.service_day == day.lower())
        .where(Customer.is_active == is_active)
        .order_by(Customer.name)
    )
    customers = result.scalars().all()
    return customers
