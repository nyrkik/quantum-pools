"""Satellite analysis schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SatelliteAnalysisResponse(BaseModel):
    id: str
    property_id: str
    pool_detected: bool
    estimated_pool_sqft: Optional[float] = None
    pool_confidence: float
    vegetation_pct: float
    canopy_overhang_pct: float
    hardscape_pct: float
    shadow_pct: float
    image_url: Optional[str] = None
    image_zoom: int
    analysis_version: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BulkAnalysisRequest(BaseModel):
    property_ids: Optional[list[str]] = None
    force_reanalyze: bool = False


class BulkAnalysisResponse(BaseModel):
    total: int
    analyzed: int
    skipped: int
    failed: int
    results: list[SatelliteAnalysisResponse]
