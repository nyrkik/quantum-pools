"""Satellite analysis schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SatelliteAnalysisResponse(BaseModel):
    id: str
    property_id: str
    body_of_water_id: Optional[str] = None
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
    customer_name: str
    customer_type: str = "residential"
    lat: Optional[float] = None
    lng: Optional[float] = None
    pool_lat: Optional[float] = None
    pool_lng: Optional[float] = None
    has_analysis: bool = False


class SatelliteImageResponse(BaseModel):
    id: str
    property_id: str
    filename: str
    url: str
    center_lat: float
    center_lng: float
    zoom: int
    is_hero: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CaptureImageRequest(BaseModel):
    center_lat: float
    center_lng: float
    zoom: int = 20


class BulkAnalysisRequest(BaseModel):
    bow_ids: Optional[list[str]] = None
    property_ids: Optional[list[str]] = None  # deprecated fallback
    force_reanalyze: bool = False


class BulkAnalysisResponse(BaseModel):
    total: int
    analyzed: int
    skipped: int
    failed: int
    results: list[SatelliteAnalysisResponse]
