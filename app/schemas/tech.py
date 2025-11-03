"""
Tech Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional
from datetime import datetime, time
from uuid import UUID


class TechBase(BaseModel):
    """Base tech schema with common fields."""

    name: str = Field(..., min_length=1, max_length=200, description="Tech name")
    email: Optional[str] = Field(None, min_length=0, max_length=255, description="Tech email address")
    phone: Optional[str] = Field(None, min_length=0, max_length=20, description="Tech phone number")
    color: str = Field(
        default='#3498db',
        pattern='^#[0-9A-Fa-f]{6}$',
        description="Hex color code for route visualization"
    )

    start_location_address: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Address where tech starts their route"
    )
    end_location_address: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Address where tech ends their route"
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
        description="Maximum customers this tech can service per day"
    )

    efficiency_multiplier: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Efficiency multiplier for optimization (e.g., 1.5 = 50% more efficient)"
    )

    notes: Optional[str] = Field(
        default=None,
        min_length=0,
        max_length=1000,
        description="Additional notes about tech"
    )
    is_active: bool = Field(default=True, description="Whether tech is currently active")


class TechCreate(TechBase):
    """Schema for creating a new tech."""
    pass


class TechUpdate(BaseModel):
    """Schema for updating an existing tech (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[str] = Field(None, min_length=0, max_length=255)
    phone: Optional[str] = Field(None, min_length=0, max_length=20)
    color: Optional[str] = Field(None, pattern='^#[0-9A-Fa-f]{6}$')
    start_location_address: Optional[str] = Field(None, min_length=1, max_length=500)
    end_location_address: Optional[str] = Field(None, min_length=1, max_length=500)
    working_hours_start: Optional[time] = None
    working_hours_end: Optional[time] = None
    max_customers_per_day: Optional[int] = Field(None, ge=1, le=100)
    efficiency_multiplier: Optional[float] = Field(None, ge=0.1, le=5.0)
    notes: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None


class TechResponse(TechBase):
    """Schema for tech responses (includes database fields)."""

    id: UUID
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    customer_count: Optional[int] = None  # Number of customers assigned for a given day

    model_config = ConfigDict(from_attributes=True)


class TechListResponse(BaseModel):
    """Schema for paginated tech list responses."""

    techs: list[TechResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)
