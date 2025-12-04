"""
Pydantic schemas for Visit model.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class VisitBase(BaseModel):
    """Base visit schema with common fields."""
    customer_id: UUID
    tech_id: UUID
    scheduled_date: datetime
    service_day: str
    actual_arrival_time: Optional[datetime] = None
    actual_departure_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    service_performed: Optional[str] = None
    notes: Optional[str] = None
    photos: Optional[List[str]] = None
    status: str = "scheduled"


class VisitCreate(VisitBase):
    """Schema for creating a new visit."""
    pass


class VisitUpdate(BaseModel):
    """Schema for updating a visit (all fields optional)."""
    actual_arrival_time: Optional[datetime] = None
    actual_departure_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    service_performed: Optional[str] = None
    notes: Optional[str] = None
    photos: Optional[List[str]] = None
    status: Optional[str] = None


class VisitResponse(VisitBase):
    """Schema for visit response."""
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    # Related data
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    tech_name: Optional[str] = None
    services: Optional[List[dict]] = None  # List of services performed

    model_config = ConfigDict(from_attributes=True)


class VisitListResponse(BaseModel):
    """Schema for list of visits."""
    visits: List[VisitResponse]
    total: int
