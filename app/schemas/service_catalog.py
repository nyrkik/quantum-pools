"""
Pydantic schemas for Service Catalog.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class ServiceCatalogBase(BaseModel):
    """Base service catalog schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    estimated_duration: Optional[int] = None  # Minutes


class ServiceCatalogCreate(ServiceCatalogBase):
    """Schema for creating a new service."""
    pass


class ServiceCatalogUpdate(BaseModel):
    """Schema for updating a service (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    estimated_duration: Optional[int] = None
    is_active: Optional[bool] = None


class ServiceCatalogResponse(ServiceCatalogBase):
    """Schema for service response."""
    id: UUID
    organization_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceCatalogListResponse(BaseModel):
    """Schema for list of services."""
    services: List[ServiceCatalogResponse]
    total: int
