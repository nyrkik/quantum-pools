"""Pool measurement schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PhotoInfo(BaseModel):
    filename: str
    path: str
    type: str  # "overview" or "depth"


class MeasurementResponse(BaseModel):
    id: str
    property_id: str
    measured_by: Optional[str] = None
    length_ft: Optional[float] = None
    width_ft: Optional[float] = None
    depth_shallow_ft: Optional[float] = None
    depth_deep_ft: Optional[float] = None
    depth_avg_ft: Optional[float] = None
    calculated_sqft: Optional[float] = None
    calculated_gallons: Optional[int] = None
    pool_shape: Optional[str] = None
    scale_reference: Optional[str] = None
    confidence: Optional[float] = None
    photo_paths: Optional[list[PhotoInfo]] = None
    raw_analysis: Optional[dict] = None
    error_message: Optional[str] = None
    status: str
    applied_to_property: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeasurementApplyResponse(BaseModel):
    measurement_id: str
    property_id: str
    pool_length_ft: Optional[float] = None
    pool_width_ft: Optional[float] = None
    pool_depth_shallow: Optional[float] = None
    pool_depth_deep: Optional[float] = None
    pool_depth_avg: Optional[float] = None
    pool_sqft: Optional[float] = None
    pool_gallons: Optional[int] = None
    pool_shape: Optional[str] = None
    pool_volume_method: str = "measured"
