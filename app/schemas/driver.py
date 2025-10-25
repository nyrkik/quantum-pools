"""
Driver Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional
from datetime import datetime, time
from uuid import UUID


class DriverBase(BaseModel):
    """Base driver schema with common fields."""

    name: str = Field(..., min_length=1, max_length=200, description="Driver name")
    email: Optional[EmailStr] = Field(None, description="Driver email address")
    phone: Optional[str] = Field(None, max_length=20, description="Driver phone number")
    color: str = Field(
        default='#3498db',
        pattern='^#[0-9A-Fa-f]{6}$',
        description="Hex color code for route visualization"
    )

    start_location_address: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Address where driver starts their route"
    )
    end_location_address: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Address where driver ends their route"
    )

    working_hours_start: time = Field(
        default=time(8, 0),
        description="Start of workday"
    )
    working_hours_end: time = Field(
        default=time(17, 0),
        description="End of workday"
    )

    max_customers_per_day: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum customers this driver can service per day"
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Additional notes about driver"
    )
    is_active: bool = Field(default=True, description="Whether driver is currently active")


class DriverCreate(DriverBase):
    """Schema for creating a new driver."""
    pass


class DriverUpdate(BaseModel):
    """Schema for updating an existing driver (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    color: Optional[str] = Field(None, pattern='^#[0-9A-Fa-f]{6}$')
    start_location_address: Optional[str] = Field(None, min_length=1, max_length=500)
    end_location_address: Optional[str] = Field(None, min_length=1, max_length=500)
    working_hours_start: Optional[time] = None
    working_hours_end: Optional[time] = None
    max_customers_per_day: Optional[int] = Field(None, ge=1, le=100)
    notes: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None


class DriverResponse(DriverBase):
    """Schema for driver responses (includes database fields)."""

    id: UUID
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriverListResponse(BaseModel):
    """Schema for paginated driver list responses."""

    drivers: list[DriverResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)
