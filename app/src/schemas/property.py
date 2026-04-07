"""Property schemas."""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    pass


class PropertyCreate(BaseModel):
    customer_id: str
    name: Optional[str] = None
    address: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    zip_code: str = Field(..., min_length=1)
    county: Optional[str] = None
    emd_fa_number: Optional[str] = None
    # Pool/equipment fields live on WaterFeature, not Property.
    # Create a WF via /api/v1/bodies-of-water/property/{id} after property creation.
    gate_code: Optional[str] = None
    access_instructions: Optional[str] = None
    dog_on_property: bool = False
    monthly_rate: Optional[float] = None
    estimated_service_minutes: int = 30
    is_locked_to_day: bool = False
    service_day_pattern: Optional[str] = None
    notes: Optional[str] = None


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    emd_fa_number: Optional[str] = None
    # Pool/equipment fields live on WaterFeature — update via WF endpoints.
    gate_code: Optional[str] = None
    access_instructions: Optional[str] = None
    dog_on_property: Optional[bool] = None
    monthly_rate: Optional[float] = None
    estimated_service_minutes: Optional[int] = None
    is_locked_to_day: Optional[bool] = None
    service_day_pattern: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PropertyResponse(BaseModel):
    id: str
    customer_id: str
    name: Optional[str] = None
    address: str
    city: str
    state: str
    zip_code: str
    county: Optional[str] = None
    emd_fa_number: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    pool_type: Optional[str] = None
    pool_gallons: Optional[int] = None
    pool_sqft: Optional[float] = None
    pool_surface: Optional[str] = None
    pool_length_ft: Optional[float] = None
    pool_width_ft: Optional[float] = None
    pool_depth_shallow: Optional[float] = None
    pool_depth_deep: Optional[float] = None
    pool_depth_avg: Optional[float] = None
    pool_shape: Optional[str] = None
    pool_volume_method: Optional[str] = None
    has_spa: bool
    has_water_feature: bool
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    gate_code: Optional[str] = None
    access_instructions: Optional[str] = None
    dog_on_property: bool
    monthly_rate: Optional[float] = None
    estimated_service_minutes: int
    is_locked_to_day: bool
    service_day_pattern: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    water_features: list[WaterFeatureSummary] = []

    model_config = {"from_attributes": True}


class WaterFeatureSummary(BaseModel):
    """Inline WF summary for property responses."""
    id: str
    name: Optional[str] = None
    water_type: str
    pool_type: Optional[str] = None
    pool_gallons: Optional[int] = None
    pool_sqft: Optional[float] = None
    estimated_service_minutes: int
    monthly_rate: Optional[float] = None

    model_config = {"from_attributes": True}


# Rebuild PropertyResponse to resolve forward ref
PropertyResponse.model_rebuild()
