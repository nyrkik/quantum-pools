"""Dimension estimate schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DimensionEstimateResponse(BaseModel):
    id: str
    source: str
    estimated_sqft: Optional[float] = None
    perimeter_ft: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PerimeterMeasurementRequest(BaseModel):
    perimeter_ft: float = Field(..., gt=0)
    pool_shape: str  # round, oval, irregular_oval, rectangle, kidney, L-shape, freeform


class DimensionComparisonResponse(BaseModel):
    estimates: list[DimensionEstimateResponse]
    active_source: Optional[str] = None
    active_sqft: Optional[float] = None
    discrepancy_pct: Optional[float] = None  # null if <2 estimates
    discrepancy_level: Optional[str] = None  # "ok", "review", "alert"
