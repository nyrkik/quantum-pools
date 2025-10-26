"""
Driver management API endpoints.
Provides CRUD operations for drivers/technicians.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.driver import Driver
from app.schemas.driver import (
    DriverCreate,
    DriverUpdate,
    DriverResponse,
    DriverListResponse
)
from app.services.geocoding import geocoding_service

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


@router.post(
    "/",
    response_model=DriverResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new driver"
)
async def create_driver(
    driver: DriverCreate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new driver/technician with the provided information.

    - **name**: Driver name (required)
    - **email**: Email address (optional)
    - **phone**: Phone number (optional)
    - **start_location_address**: Where driver starts route (required)
    - **end_location_address**: Where driver ends route (required)
    - **working_hours_start**: Start of workday (default: 08:00)
    - **working_hours_end**: End of workday (default: 17:00)
    - **max_customers_per_day**: Maximum customers per day (default: 20)
    """
    driver_data = driver.model_dump()
    driver_data['organization_id'] = auth.organization_id
    db_driver = Driver(**driver_data)

    # Geocode start location
    start_coords = await geocoding_service.geocode_address(db_driver.start_location_address)
    if start_coords:
        db_driver.start_latitude, db_driver.start_longitude = start_coords

    # Geocode end location
    end_coords = await geocoding_service.geocode_address(db_driver.end_location_address)
    if end_coords:
        db_driver.end_latitude, db_driver.end_longitude = end_coords

    db.add(db_driver)
    await db.commit()
    await db.refresh(db_driver)
    return db_driver


@router.get(
    "/",
    response_model=DriverListResponse,
    summary="List all drivers with pagination"
)
async def list_drivers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a paginated list of drivers with optional filters.

    Filters:
    - **is_active**: Filter by active/inactive status
    """
    # Build base query
    query = select(Driver).where(Driver.organization_id == auth.organization_id)

    # Apply filters
    if is_active is not None:
        query = query.where(Driver.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Driver.name)

    # Execute query
    result = await db.execute(query)
    drivers = result.scalars().all()

    return DriverListResponse(
        drivers=drivers,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get(
    "/active",
    response_model=list[DriverResponse],
    summary="Get all active drivers"
)
async def get_active_drivers(
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all active drivers.

    Useful for route optimization when you need available drivers.
    """
    result = await db.execute(
        select(Driver)
        .where(Driver.organization_id == auth.organization_id)
        .where(Driver.is_active == True)
        .order_by(Driver.name)
    )
    drivers = result.scalars().all()
    return drivers


@router.get(
    "/{driver_id}",
    response_model=DriverResponse,
    summary="Get a specific driver"
)
async def get_driver(
    driver_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific driver by ID.
    """
    result = await db.execute(
        select(Driver)
        .where(Driver.id == driver_id)
        .where(Driver.organization_id == auth.organization_id)
    )
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )

    return driver


@router.put(
    "/{driver_id}",
    response_model=DriverResponse,
    summary="Update a driver"
)
async def update_driver(
    driver_id: UUID,
    driver_update: DriverUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing driver's information.

    Only provided fields will be updated. All fields are optional.
    """
    # Fetch existing driver
    result = await db.execute(
        select(Driver)
        .where(Driver.id == driver_id)
        .where(Driver.organization_id == auth.organization_id)
    )
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )

    # Update fields
    update_data = driver_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(driver, field, value)

    # Re-geocode if locations changed
    if "start_location_address" in update_data:
        start_coords = await geocoding_service.geocode_address(driver.start_location_address)
        if start_coords:
            driver.start_latitude, driver.start_longitude = start_coords

    if "end_location_address" in update_data:
        end_coords = await geocoding_service.geocode_address(driver.end_location_address)
        if end_coords:
            driver.end_latitude, driver.end_longitude = end_coords

    await db.commit()
    await db.refresh(driver)
    return driver


@router.delete(
    "/{driver_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a driver"
)
async def delete_driver(
    driver_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a driver by ID.

    This will also delete all associated routes.
    """
    result = await db.execute(
        select(Driver)
        .where(Driver.id == driver_id)
        .where(Driver.organization_id == auth.organization_id)
    )
    driver = result.scalar_one_or_none()

    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )

    await db.delete(driver)
    await db.commit()
