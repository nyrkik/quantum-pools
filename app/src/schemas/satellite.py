"""Satellite analysis schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SatelliteAnalysisResponse(BaseModel):
    id: str
    property_id: str
    water_feature_id: Optional[str] = None
    pool_detected: bool
    estimated_pool_sqft: Optional[float] = None
    pool_confidence: float
    vegetation_pct: float
    canopy_overhang_pct: float
    hardscape_pct: float
    shadow_pct: float
    pool_lat: Optional[float] = None
    pool_lng: Optional[float] = None
    image_url: Optional[str] = None
    image_zoom: int
    analysis_version: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SetPinRequest(BaseModel):
    pool_lat: float
    pool_lng: float


class AnalyzeRequest(BaseModel):
    pool_lat: Optional[float] = None
    pool_lng: Optional[float] = None
    force: bool = False


class PoolBowWithCoordsResponse(BaseModel):
    id: str
    property_id: str
    bow_name: Optional[str] = None
    water_type: str
    address: str
    city: str = ""
    customer_id: str
    customer_name: str
    customer_type: str = "residential"
    pool_sqft: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    pool_lat: Optional[float] = None
    pool_lng: Optional[float] = None
    has_analysis: bool = False
    tech_name: Optional[str] = None
    tech_color: Optional[str] = None


class BulkAnalysisRequest(BaseModel):
    wf_ids: Optional[list[str]] = None
    property_ids: Optional[list[str]] = None  # deprecated fallback
    force_reanalyze: bool = False


class BulkAnalysisResponse(BaseModel):
    total: int
    analyzed: int
    skipped: int
    failed: int
    results: list[SatelliteAnalysisResponse]
