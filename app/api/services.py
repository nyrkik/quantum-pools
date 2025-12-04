"""
API endpoints for service catalog management.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.service_catalog import ServiceCatalog
from app.schemas.service_catalog import (
    ServiceCatalogCreate,
    ServiceCatalogUpdate,
    ServiceCatalogResponse,
    ServiceCatalogListResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("", response_model=ServiceCatalogListResponse, summary="List services")
async def list_services(
    category: Optional[str] = None,
    is_active: Optional[bool] = True,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of services from catalog."""
    try:
        query = select(ServiceCatalog).where(
            ServiceCatalog.organization_id == auth.organization_id
        )

        if category:
            query = query.where(ServiceCatalog.category == category)
        if is_active is not None:
            query = query.where(ServiceCatalog.is_active == is_active)

        query = query.order_by(ServiceCatalog.category, ServiceCatalog.name)

        result = await db.execute(query)
        services = result.scalars().all()

        count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(count_query)

        return ServiceCatalogListResponse(services=services, total=total or 0)

    except Exception as e:
        logger.error(f"Error listing services: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving services"
        )


@router.get("/{service_id}", response_model=ServiceCatalogResponse, summary="Get service")
async def get_service(
    service_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific service by ID."""
    result = await db.execute(
        select(ServiceCatalog).where(
            ServiceCatalog.id == service_id,
            ServiceCatalog.organization_id == auth.organization_id
        )
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    return service


@router.post("", response_model=ServiceCatalogResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    service_data: ServiceCatalogCreate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new service in the catalog."""
    try:
        service = ServiceCatalog(
            organization_id=auth.organization_id,
            **service_data.model_dump()
        )

        db.add(service)
        await db.commit()
        await db.refresh(service)

        logger.info(f"Created service {service.id} for organization {auth.organization_id}")
        return service

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating service"
        )


@router.put("/{service_id}", response_model=ServiceCatalogResponse)
async def update_service(
    service_id: UUID,
    service_data: ServiceCatalogUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing service."""
    result = await db.execute(
        select(ServiceCatalog).where(
            ServiceCatalog.id == service_id,
            ServiceCatalog.organization_id == auth.organization_id
        )
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    try:
        update_data = service_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(service, field, value)

        await db.commit()
        await db.refresh(service)

        logger.info(f"Updated service {service_id}")
        return service

    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating service"
        )


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a service from the catalog."""
    result = await db.execute(
        select(ServiceCatalog).where(
            ServiceCatalog.id == service_id,
            ServiceCatalog.organization_id == auth.organization_id
        )
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    try:
        await db.delete(service)
        await db.commit()
        logger.info(f"Deleted service {service_id}")

    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting service"
        )
