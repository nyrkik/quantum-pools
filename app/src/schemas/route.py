"""Route schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RouteOptimizationRequest(BaseModel):
    mode: str = Field("full_per_day", pattern="^(refine|full_per_day|cross_day)$")
    speed: str = Field("quick", pattern="^(quick|thorough)$")
    service_day: Optional[str] = None
    tech_ids: Optional[List[str]] = None
    avg_speed_mph: float = 30.0


class StopReorderRequest(BaseModel):
    new_sequence: int = Field(..., ge=1)


class StopReassignRequest(BaseModel):
    new_tech_id: str
    new_service_day: str


class RouteStopResponse(BaseModel):
    id: str
    property_id: str
    sequence: int
    estimated_service_duration: int
    estimated_drive_time_from_previous: int
    estimated_distance_from_previous: float
    property_address: Optional[str] = None
    customer_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

    model_config = {"from_attributes": True}


class RouteResponse(BaseModel):
    id: str
    tech_id: str
    tech_name: Optional[str] = None
    tech_color: Optional[str] = None
    service_day: str
    total_duration_minutes: int
    total_distance_miles: float
    total_stops: int
    optimization_algorithm: Optional[str] = None
    stops: List[RouteStopResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OptimizationStopResult(BaseModel):
    property_id: str
    property_address: str = ""
    customer_name: str = ""
    lat: float
    lng: float
    sequence: int
    estimated_service_duration: int = 30
    estimated_drive_time_from_previous: int = 0
    estimated_distance_from_previous: float = 0.0


class OptimizationRouteResult(BaseModel):
    tech_id: str
    tech_name: str = ""
    tech_color: str = "#3B82F6"
    service_day: str
    stops: List[OptimizationStopResult] = []
    total_stops: int = 0
    total_distance_miles: float = 0.0
    total_duration_minutes: int = 0


class OptimizationSummary(BaseModel):
    total_routes: int = 0
    total_stops: int = 0
    total_distance_miles: float = 0.0
    total_duration_minutes: int = 0
    optimization_mode: str = ""


class RouteOptimizationResponse(BaseModel):
    routes: List[OptimizationRouteResult] = []
    summary: OptimizationSummary = OptimizationSummary()
