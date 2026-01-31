"""Property schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PropertyCreate(BaseModel):
    customer_id: str
    address: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    zip_code: str = Field(..., min_length=1)
    pool_type: Optional[str] = None
    pool_gallons: Optional[int] = None
    pool_surface: Optional[str] = None
    has_spa: bool = False
    has_water_feature: bool = False
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    gate_code: Optional[str] = None
    access_instructions: Optional[str] = None
    dog_on_property: bool = False
    estimated_service_minutes: int = 30
    is_locked_to_day: bool = False
    service_day_pattern: Optional[str] = None
    notes: Optional[str] = None


class PropertyUpdate(BaseModel):
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    pool_type: Optional[str] = None
    pool_gallons: Optional[int] = None
    pool_surface: Optional[str] = None
    has_spa: Optional[bool] = None
    has_water_feature: Optional[bool] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    gate_code: Optional[str] = None
    access_instructions: Optional[str] = None
    dog_on_property: Optional[bool] = None
    estimated_service_minutes: Optional[int] = None
    is_locked_to_day: Optional[bool] = None
    service_day_pattern: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PropertyResponse(BaseModel):
    id: str
    customer_id: str
    address: str
    city: str
    state: str
    zip_code: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    pool_type: Optional[str] = None
    pool_gallons: Optional[int] = None
    pool_surface: Optional[str] = None
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
    estimated_service_minutes: int
    is_locked_to_day: bool
    service_day_pattern: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
