"""
Tech management API endpoints.
Provides CRUD operations for techs/technicians.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.tech import Tech
from app.schemas.tech import (
    TechCreate,
    TechUpdate,
    TechResponse,
    TechListResponse
)
from app.services.geocoding import geocoding_service

router = APIRouter(prefix="/api/techs", tags=["techs"])


@router.post(
    "/",
    response_model=TechResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tech"
)
async def create_tech(
    tech: TechCreate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new tech/technician with the provided information.

    - **name**: Tech name (required)
    - **email**: Email address (optional)
    - **phone**: Phone number (optional)
    - **start_location_address**: Where tech starts route (required)
    - **end_location_address**: Where tech ends route (required)
    - **working_hours_start**: Start of workday (default: 08:00)
    - **working_hours_end**: End of workday (default: 17:00)
    - **max_customers_per_day**: Maximum customers per day (default: 20)
    """
    tech_data = tech.model_dump()
    tech_data['organization_id'] = auth.organization_id
    db_tech = Tech(**tech_data)

    # Geocode start location
    start_coords = await geocoding_service.geocode_address(db_tech.start_location_address)
    if start_coords:
        db_tech.start_latitude, db_tech.start_longitude = start_coords

    # Geocode end location
    end_coords = await geocoding_service.geocode_address(db_tech.end_location_address)
    if end_coords:
        db_tech.end_latitude, db_tech.end_longitude = end_coords

    db.add(db_tech)
    await db.commit()
    await db.refresh(db_tech)
    return db_tech


@router.get(
    "/",
    response_model=TechListResponse,
    summary="List all techs with pagination"
)
async def list_techs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a paginated list of techs with optional filters.

    Filters:
    - **is_active**: Filter by active/inactive status
    """
    # Build base query
    query = select(Tech).where(Tech.organization_id == auth.organization_id)

    # Apply filters
    if is_active is not None:
        query = query.where(Tech.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Tech.name)

    # Execute query
    result = await db.execute(query)
    techs = result.scalars().all()

    return TechListResponse(
        techs=techs,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get(
    "/active",
    response_model=list[TechResponse],
    summary="Get all active techs"
)
async def get_active_techs(
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all active techs.

    Useful for route optimization when you need available techs.
    """
    result = await db.execute(
        select(Tech)
        .where(Tech.organization_id == auth.organization_id)
        .where(Tech.is_active == True)
        .order_by(Tech.name)
    )
    techs = result.scalars().all()
    return techs


@router.get(
    "/{tech_id}",
    response_model=TechResponse,
    summary="Get a specific tech"
)
async def get_tech(
    tech_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific tech by ID.
    """
    result = await db.execute(
        select(Tech)
        .where(Tech.id == tech_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    tech = result.scalar_one_or_none()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tech with ID {tech_id} not found"
        )

    return tech


@router.put(
    "/{tech_id}",
    response_model=TechResponse,
    summary="Update a tech"
)
async def update_tech(
    tech_id: UUID,
    tech_update: TechUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing tech's information.

    Only provided fields will be updated. All fields are optional.
    """
    # Fetch existing tech
    result = await db.execute(
        select(Tech)
        .where(Tech.id == tech_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    tech = result.scalar_one_or_none()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tech with ID {tech_id} not found"
        )

    # Update fields
    update_data = tech_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tech, field, value)

    # Re-geocode if locations changed
    if "start_location_address" in update_data:
        start_coords = await geocoding_service.geocode_address(tech.start_location_address)
        if start_coords:
            tech.start_latitude, tech.start_longitude = start_coords

    if "end_location_address" in update_data:
        end_coords = await geocoding_service.geocode_address(tech.end_location_address)
        if end_coords:
            tech.end_latitude, tech.end_longitude = end_coords

    await db.commit()
    await db.refresh(tech)
    return tech


@router.delete(
    "/{tech_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tech"
)
async def delete_tech(
    tech_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a tech by ID.

    This will also delete all associated routes.
    """
    result = await db.execute(
        select(Tech)
        .where(Tech.id == tech_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    tech = result.scalar_one_or_none()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tech with ID {tech_id} not found"
        )

    await db.delete(tech)
    await db.commit()
