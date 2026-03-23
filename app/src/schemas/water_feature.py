"""WaterFeature schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class WaterFeatureCreate(BaseModel):
    name: Optional[str] = None
    emd_pr_number: Optional[str] = None
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
    has_rounded_corners: Optional[bool] = None
    step_entry_count: Optional[int] = None
    has_bench_shelf: Optional[bool] = None
    sanitizer_type: Optional[str] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    fill_method: Optional[str] = None
    drain_type: Optional[str] = None
    drain_method: Optional[str] = None
    drain_count: Optional[int] = None
    drain_cover_compliant: Optional[bool] = None
    drain_cover_install_date: Optional[datetime] = None
    drain_cover_expiry_date: Optional[datetime] = None
    equalizer_cover_compliant: Optional[bool] = None
    equalizer_cover_install_date: Optional[datetime] = None
    equalizer_cover_expiry_date: Optional[datetime] = None
    plumbing_size_inches: Optional[float] = None
    pool_cover_type: Optional[str] = None
    turnover_hours: Optional[float] = None
    skimmer_count: Optional[int] = None
    equipment_year: Optional[int] = None
    equipment_pad_location: Optional[str] = None
    estimated_service_minutes: int = 30
    monthly_rate: Optional[float] = None
    notes: Optional[str] = None


class WaterFeatureUpdate(BaseModel):
    name: Optional[str] = None
    emd_pr_number: Optional[str] = None
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
    has_rounded_corners: Optional[bool] = None
    step_entry_count: Optional[int] = None
    has_bench_shelf: Optional[bool] = None
    sanitizer_type: Optional[str] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    fill_method: Optional[str] = None
    drain_type: Optional[str] = None
    drain_method: Optional[str] = None
    drain_count: Optional[int] = None
    drain_cover_compliant: Optional[bool] = None
    drain_cover_install_date: Optional[datetime] = None
    drain_cover_expiry_date: Optional[datetime] = None
    equalizer_cover_compliant: Optional[bool] = None
    equalizer_cover_install_date: Optional[datetime] = None
    equalizer_cover_expiry_date: Optional[datetime] = None
    plumbing_size_inches: Optional[float] = None
    pool_cover_type: Optional[str] = None
    turnover_hours: Optional[float] = None
    skimmer_count: Optional[int] = None
    equipment_year: Optional[int] = None
    equipment_pad_location: Optional[str] = None
    estimated_service_minutes: Optional[int] = None
    monthly_rate: Optional[float] = None
    access_difficulty: Optional[float] = None
    chemical_demand: Optional[float] = None
    equipment_effectiveness: Optional[float] = None
    pool_design: Optional[float] = None
    shade_exposure: Optional[float] = None
    tree_debris: Optional[float] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class WaterFeatureResponse(BaseModel):
    id: str
    property_id: str
    name: Optional[str] = None
    emd_pr_number: Optional[str] = None
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
    has_rounded_corners: Optional[bool] = None
    step_entry_count: Optional[int] = None
    has_bench_shelf: Optional[bool] = None
    dimension_source: Optional[str] = None
    dimension_source_date: Optional[datetime] = None
    perimeter_ft: Optional[float] = None
    sanitizer_type: Optional[str] = None
    pump_type: Optional[str] = None
    filter_type: Optional[str] = None
    heater_type: Optional[str] = None
    chlorinator_type: Optional[str] = None
    automation_system: Optional[str] = None
    fill_method: Optional[str] = None
    drain_type: Optional[str] = None
    drain_method: Optional[str] = None
    drain_count: Optional[int] = None
    drain_cover_compliant: Optional[bool] = None
    drain_cover_install_date: Optional[datetime] = None
    drain_cover_expiry_date: Optional[datetime] = None
    equalizer_cover_compliant: Optional[bool] = None
    equalizer_cover_install_date: Optional[datetime] = None
    equalizer_cover_expiry_date: Optional[datetime] = None
    plumbing_size_inches: Optional[float] = None
    pool_cover_type: Optional[str] = None
    turnover_hours: Optional[float] = None
    skimmer_count: Optional[int] = None
    equipment_year: Optional[int] = None
    equipment_pad_location: Optional[str] = None
    estimated_service_minutes: int
    monthly_rate: Optional[float] = None
    access_difficulty: float = 1.0
    chemical_demand: float = 1.0
    equipment_effectiveness: float = 3.0
    pool_design: float = 3.0
    shade_exposure: float = 1.0
    tree_debris: float = 1.0
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
