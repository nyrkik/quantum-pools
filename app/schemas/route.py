"""
Route Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class RouteOptimizationRequest(BaseModel):
    """Schema for route optimization request."""

    service_day: Optional[str] = Field(
        None,
        pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
        description="Specific day to optimize (or null for all days)"
    )
    num_drivers: Optional[int] = Field(
        None,
        ge=1,
        le=20,
        description="Number of drivers to use (uses all active if not specified)"
    )
    allow_day_reassignment: bool = Field(
        default=False,
        description="Allow customers to be moved to different service days"
    )
    include_unassigned: bool = Field(
        default=False,
        description="Include customers without assigned techs in optimization"
    )
    include_pending: bool = Field(
        default=False,
        description="Include customers with pending status in optimization"
    )
    optimization_mode: str = Field(
        default="full",
        pattern="^(refine|full)$",
        description="Optimization mode: 'refine' keeps driver assignments, 'full' allows reassignment"
    )
    optimization_speed: str = Field(
        default="quick",
        pattern="^(quick|thorough)$",
        description="Optimization speed: 'quick' (30s), 'thorough' (120s)"
    )


class RouteStopResponse(BaseModel):
    """Schema for individual route stop."""

    customer_id: str
    customer_name: str
    address: str
    latitude: Optional[float]
    longitude: Optional[float]
    service_duration: int
    sequence: int


class RouteResponse(BaseModel):
    """Schema for optimized route."""

    driver_id: str
    driver_name: str
    driver_color: str = Field(default='#3498db', description="Driver's assigned color")
    service_day: str
    start_location: Optional[dict] = Field(default=None, description="Starting depot location {address, latitude, longitude}")
    end_location: Optional[dict] = Field(default=None, description="Ending depot location {address, latitude, longitude}")
    stops: List[RouteStopResponse]
    total_customers: int
    total_distance_miles: float
    total_duration_minutes: int


class RouteOptimizationResponse(BaseModel):
    """Schema for route optimization response."""

    routes: List[RouteResponse]
    summary: Optional[dict] = None
    message: Optional[str] = None


class RouteSaveRequest(BaseModel):
    """Schema for saving optimized routes to database."""

    routes: List[dict]
    service_day: str


class SavedRouteResponse(BaseModel):
    """Schema for saved route from database."""

    id: UUID
    driver_id: UUID
    service_day: str
    total_duration_minutes: Optional[int]
    total_distance_miles: Optional[float]
    total_customers: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
