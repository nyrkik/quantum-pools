"""
Customer Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, time
from uuid import UUID


class CustomerBase(BaseModel):
    """Base customer schema with common fields."""

    name: str = Field(..., min_length=1, max_length=200, description="Customer name")
    address: str = Field(..., min_length=1, max_length=500, description="Street address")
    service_type: str = Field(
        ...,
        pattern="^(residential|commercial)$",
        description="Type of service: residential or commercial"
    )
    difficulty: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Difficulty level (1-5) affecting service duration"
    )
    service_day: str = Field(
        ...,
        pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
        description="Day of week for service"
    )
    locked: bool = Field(
        default=False,
        description="If true, cannot be reassigned to different service day"
    )
    time_window_start: Optional[time] = Field(
        default=None,
        description="Earliest time customer can be serviced"
    )
    time_window_end: Optional[time] = Field(
        default=None,
        description="Latest time customer can be serviced"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Additional notes about customer"
    )
    is_active: bool = Field(default=True, description="Whether customer is active")


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer."""
    pass


class CustomerUpdate(BaseModel):
    """Schema for updating an existing customer (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    address: Optional[str] = Field(None, min_length=1, max_length=500)
    service_type: Optional[str] = Field(None, pattern="^(residential|commercial)$")
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    service_day: Optional[str] = Field(
        None,
        pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$"
    )
    locked: Optional[bool] = None
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None
    notes: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    """Schema for customer responses (includes database fields)."""

    id: UUID
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerListResponse(BaseModel):
    """Schema for paginated customer list responses."""

    customers: list[CustomerResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)
