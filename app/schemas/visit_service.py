"""
Pydantic schemas for Visit Services.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class VisitServiceBase(BaseModel):
    """Base visit service schema."""
    service_catalog_id: Optional[UUID] = None
    custom_service_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None


class VisitServiceCreate(VisitServiceBase):
    """Schema for creating a new visit service."""
    pass


class VisitServiceUpdate(BaseModel):
    """Schema for updating a visit service."""
    service_catalog_id: Optional[UUID] = None
    custom_service_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None


class VisitServiceResponse(VisitServiceBase):
    """Schema for visit service response."""
    id: UUID
    visit_id: UUID
    completed_at: datetime
    created_at: datetime
    updated_at: datetime

    # Related data
    service_name: Optional[str] = None  # From catalog or custom

    model_config = ConfigDict(from_attributes=True)


class VisitServiceListResponse(BaseModel):
    """Schema for list of visit services."""
    services: List[VisitServiceResponse]
    total: int
