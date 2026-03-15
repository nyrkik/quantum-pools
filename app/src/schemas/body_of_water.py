"""BodyOfWater schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BodyOfWaterCreate(BaseModel):
    name: Optional[str] = None
    water_type: str = "pool"
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
    sanitizer_type: Optional[str] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    estimated_service_minutes: int = 30
    monthly_rate: Optional[float] = None
    notes: Optional[str] = None


class BodyOfWaterUpdate(BaseModel):
    name: Optional[str] = None
    water_type: Optional[str] = None
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
    sanitizer_type: Optional[str] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    estimated_service_minutes: Optional[int] = None
    monthly_rate: Optional[float] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class BodyOfWaterResponse(BaseModel):
    id: str
    property_id: str
    name: Optional[str] = None
    water_type: str
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
    sanitizer_type: Optional[str] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    estimated_service_minutes: int
    monthly_rate: Optional[float] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
