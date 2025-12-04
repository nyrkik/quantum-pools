"""
API endpoints for visit management.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
from datetime import datetime, date

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.visit import Visit
from app.models.customer import Customer
from app.models.tech import Tech
from app.models.visit_service import VisitService
from app.models.service_catalog import ServiceCatalog
from app.schemas.visit import (
    VisitCreate,
    VisitUpdate,
    VisitResponse,
    VisitListResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/visits", tags=["visits"])


@router.get("", response_model=VisitListResponse, summary="List visits")
async def list_visits(
    service_day: Optional[str] = None,
    tech_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of visits with optional filters.

    Filters:
    - service_day: Filter by day of week (monday, tuesday, etc.)
    - tech_id: Filter by tech
    - customer_id: Filter by customer
    - status: Filter by status (scheduled, in_progress, completed, cancelled, no_show)
    - start_date: Filter visits on or after this date
    - end_date: Filter visits on or before this date
    """
    query = (
        select(Visit)
        .options(
            selectinload(Visit.customer),
            selectinload(Visit.tech),
            selectinload(Visit.services)
        )
        .where(Visit.organization_id == auth.organization_id)
    )

    # Auto-filter by tech_id if user is a tech (unless explicitly overridden)
    if auth.tech_id and tech_id is None:
        query = query.where(Visit.tech_id == auth.tech_id)
    elif tech_id:
        query = query.where(Visit.tech_id == tech_id)

    if service_day:
        query = query.where(Visit.service_day == service_day.lower())
    if customer_id:
        query = query.where(Visit.customer_id == customer_id)
    if status:
        query = query.where(Visit.status == status)
    if start_date:
        query = query.where(Visit.scheduled_date >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.where(Visit.scheduled_date <= datetime.combine(end_date, datetime.max.time()))

    query = query.order_by(Visit.scheduled_date.desc())

    result = await db.execute(query)
    visits = result.scalars().all()

    # Enrich with related data
    visit_responses = []
    for visit in visits:
        visit_data = VisitResponse.model_validate(visit)
        visit_data.customer_name = visit.customer.display_name if visit.customer else None
        visit_data.customer_address = visit.customer.address if visit.customer else None
        visit_data.tech_name = visit.tech.name if visit.tech else None
        visit_data.services = [
            {
                "id": str(vs.id),
                "service_catalog_id": str(vs.service_catalog_id) if vs.service_catalog_id else None,
                "custom_service_name": vs.custom_service_name,
                "notes": vs.notes,
                "service_name": vs.service.name if vs.service else vs.custom_service_name
            }
            for vs in visit.services
        ] if visit.services else []
        visit_responses.append(visit_data)

    return VisitListResponse(visits=visit_responses, total=len(visit_responses))


@router.get("/{visit_id}", response_model=VisitResponse, summary="Get visit by ID")
async def get_visit(
    visit_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific visit by ID."""
    result = await db.execute(
        select(Visit)
        .options(
            selectinload(Visit.customer),
            selectinload(Visit.tech),
            selectinload(Visit.services)
        )
        .where(
            Visit.id == visit_id,
            Visit.organization_id == auth.organization_id
        )
    )
    visit = result.scalar_one_or_none()

    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found"
        )

    visit_data = VisitResponse.model_validate(visit)
    visit_data.customer_name = visit.customer.display_name if visit.customer else None
    visit_data.customer_address = visit.customer.address if visit.customer else None
    visit_data.tech_name = visit.tech.name if visit.tech else None
    visit_data.services = [
        {
            "id": str(vs.id),
            "service_catalog_id": str(vs.service_catalog_id) if vs.service_catalog_id else None,
            "custom_service_name": vs.custom_service_name,
            "notes": vs.notes,
            "service_name": vs.service.name if vs.service else vs.custom_service_name
        }
        for vs in visit.services
    ] if visit.services else []

    return visit_data


@router.post("", response_model=VisitResponse, status_code=status.HTTP_201_CREATED, summary="Create visit")
async def create_visit(
    visit_data: VisitCreate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new visit (manual entry)."""
    # Verify customer exists and belongs to organization
    customer_result = await db.execute(
        select(Customer).where(
            Customer.id == visit_data.customer_id,
            Customer.organization_id == auth.organization_id
        )
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    # Verify tech exists and belongs to organization
    tech_result = await db.execute(
        select(Tech).where(
            Tech.id == visit_data.tech_id,
            Tech.organization_id == auth.organization_id
        )
    )
    tech = tech_result.scalar_one_or_none()
    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tech not found"
        )

    # Create visit
    visit = Visit(
        organization_id=auth.organization_id,
        **visit_data.model_dump()
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)

    # Load relationships
    await db.refresh(visit, ["customer", "tech"])

    visit_response = VisitResponse.model_validate(visit)
    visit_response.customer_name = visit.customer.display_name
    visit_response.customer_address = visit.customer.address
    visit_response.tech_name = visit.tech.name

    return visit_response


@router.put("/{visit_id}", response_model=VisitResponse, summary="Update visit")
async def update_visit(
    visit_id: UUID,
    visit_data: VisitUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a visit (typically filled in by tech during/after service)."""
    result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.organization_id == auth.organization_id
        )
    )
    visit = result.scalar_one_or_none()

    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found"
        )

    # Update fields
    update_data = visit_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(visit, field, value)

    # Set completed_at if status changed to completed
    if visit_data.status == "completed" and visit.status != "completed":
        visit.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(visit)

    # Load relationships
    await db.refresh(visit, ["customer", "tech"])

    visit_response = VisitResponse.model_validate(visit)
    visit_response.customer_name = visit.customer.display_name
    visit_response.customer_address = visit.customer.address
    visit_response.tech_name = visit.tech.name

    return visit_response


@router.delete("/{visit_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete visit")
async def delete_visit(
    visit_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a visit."""
    result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.organization_id == auth.organization_id
        )
    )
    visit = result.scalar_one_or_none()

    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found"
        )

    await db.delete(visit)
    await db.commit()

    return None


class AddServiceRequest(BaseModel):
    """Request schema for adding a service to a visit."""
    service_catalog_id: Optional[UUID] = None
    custom_service_name: Optional[str] = None
    notes: Optional[str] = None


@router.post("/{visit_id}/services", status_code=status.HTTP_201_CREATED, summary="Add service to visit")
async def add_service_to_visit(
    visit_id: UUID,
    service_data: AddServiceRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a service to a visit (from catalog or custom)."""
    # Verify visit exists and belongs to organization
    result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.organization_id == auth.organization_id
        )
    )
    visit = result.scalar_one_or_none()
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found"
        )

    # Verify service exists if provided
    if service_data.service_catalog_id:
        service_result = await db.execute(
            select(ServiceCatalog).where(
                ServiceCatalog.id == service_data.service_catalog_id,
                ServiceCatalog.organization_id == auth.organization_id
            )
        )
        service = service_result.scalar_one_or_none()
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )

    # Must provide either service_catalog_id or custom_service_name
    if not service_data.service_catalog_id and not service_data.custom_service_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either service_catalog_id or custom_service_name"
        )

    # Create visit service
    visit_service = VisitService(
        visit_id=visit_id,
        service_catalog_id=service_data.service_catalog_id,
        custom_service_name=service_data.custom_service_name,
        notes=service_data.notes
    )
    db.add(visit_service)
    await db.commit()
    await db.refresh(visit_service)

    return {
        "id": str(visit_service.id),
        "visit_id": str(visit_service.visit_id),
        "service_catalog_id": str(visit_service.service_catalog_id) if visit_service.service_catalog_id else None,
        "custom_service_name": visit_service.custom_service_name,
        "notes": visit_service.notes
    }


@router.delete("/{visit_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove service from visit")
async def remove_service_from_visit(
    visit_id: UUID,
    service_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a service from a visit."""
    # Verify visit exists and belongs to organization
    result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.organization_id == auth.organization_id
        )
    )
    visit = result.scalar_one_or_none()
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found"
        )

    # Verify visit service exists
    vs_result = await db.execute(
        select(VisitService).where(
            VisitService.id == service_id,
            VisitService.visit_id == visit_id
        )
    )
    visit_service = vs_result.scalar_one_or_none()
    if not visit_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit service not found"
        )

    await db.delete(visit_service)
    await db.commit()

    return None
