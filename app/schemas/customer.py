"""
Customer Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field, ConfigDict, computed_field, field_validator
from typing import Optional
from datetime import datetime, time
from uuid import UUID


class AssignedDriverInfo(BaseModel):
    """Minimal driver information for customer responses."""
    id: UUID
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    """Base customer schema with common fields."""

    name: Optional[str] = Field(None, min_length=0, max_length=200, description="Business name (for commercial)")
    first_name: Optional[str] = Field(None, min_length=0, max_length=100, description="First name (for residential)")
    last_name: Optional[str] = Field(None, min_length=0, max_length=100, description="Last name (for residential)")
    display_name: Optional[str] = Field(None, min_length=0, max_length=200, description="Display name (auto-generated if not provided)")
    address: str = Field(..., min_length=1, max_length=500, description="Street address")
    email: Optional[str] = Field(None, min_length=0, max_length=255, description="Primary email address")
    phone: Optional[str] = Field(None, min_length=0, max_length=20, description="Primary phone number")
    alt_email: Optional[str] = Field(None, min_length=0, max_length=255, description="Alternate email address")
    alt_phone: Optional[str] = Field(None, min_length=0, max_length=20, description="Alternate phone number")
    invoice_email: Optional[str] = Field(None, min_length=0, max_length=255, description="Invoice email (for commercial)")
    management_company: Optional[str] = Field(None, min_length=0, max_length=200, description="Management company name (for commercial)")
    assigned_driver_id: Optional[UUID] = Field(
        default=None,
        description="Driver assigned to service this customer"
    )
    service_type: str = Field(
        ...,
        pattern="^(residential|commercial)$",
        description="Type of service: residential or commercial"
    )
    visit_duration: int = Field(
        default=15,
        ge=5,
        le=120,
        description="Visit duration in minutes"
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
        description="Primary day of week for service"
    )
    service_days_per_week: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Number of service days per week (1, 2, or 3)"
    )
    service_schedule: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Current schedule pattern (e.g., 'Mo/Th', 'Mo/We/Fr')"
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
        min_length=0,
        max_length=1000,
        description="Additional notes about customer"
    )
    is_active: bool = Field(default=True, description="Whether customer is active")


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer."""
    pass


class CustomerUpdate(BaseModel):
    """Schema for updating an existing customer (all fields optional)."""

    name: Optional[str] = Field(None, min_length=0, max_length=200)
    first_name: Optional[str] = Field(None, min_length=0, max_length=100)
    last_name: Optional[str] = Field(None, min_length=0, max_length=100)
    display_name: Optional[str] = Field(None, min_length=0, max_length=200)
    address: Optional[str] = Field(None, min_length=1, max_length=500)
    email: Optional[str] = Field(None, min_length=0, max_length=255)
    phone: Optional[str] = Field(None, min_length=0, max_length=20)
    alt_email: Optional[str] = Field(None, min_length=0, max_length=255)
    alt_phone: Optional[str] = Field(None, min_length=0, max_length=20)
    invoice_email: Optional[str] = Field(None, min_length=0, max_length=255)
    management_company: Optional[str] = Field(None, min_length=0, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    assigned_driver_id: Optional[UUID] = None
    service_type: Optional[str] = Field(None, pattern="^(residential|commercial)$")
    visit_duration: Optional[int] = Field(None, ge=5, le=120)
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    service_day: Optional[str] = Field(
        None,
        pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$"
    )
    service_days_per_week: Optional[int] = Field(None, ge=1, le=3)
    service_schedule: Optional[str] = Field(None, max_length=50)
    locked: Optional[bool] = None
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None
    notes: Optional[str] = Field(None, min_length=0, max_length=1000)
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    """Schema for customer responses (includes database fields)."""

    id: UUID
    display_name: str  # Override to make required
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    assigned_driver: Optional[AssignedDriverInfo] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator('first_name', 'last_name', 'name', 'email', 'phone', 'alt_email', 'alt_phone', 'invoice_email', 'management_company', 'notes', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty strings to None for optional string fields."""
        if v == '':
            return None
        return v


class CustomerListResponse(BaseModel):
    """Schema for paginated customer list responses."""

    customers: list[CustomerResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)
