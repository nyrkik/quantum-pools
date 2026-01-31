"""Tech schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, time


class TechCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = None
    color: str = "#3B82F6"
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    start_address: Optional[str] = None
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None
    end_address: Optional[str] = None
    work_start_time: Optional[time] = None
    work_end_time: Optional[time] = None
    working_days: Optional[dict] = None
    max_stops_per_day: int = 20
    efficiency_factor: float = 1.0


class TechUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    color: Optional[str] = None
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    start_address: Optional[str] = None
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None
    end_address: Optional[str] = None
    work_start_time: Optional[time] = None
    work_end_time: Optional[time] = None
    working_days: Optional[dict] = None
    max_stops_per_day: Optional[int] = None
    efficiency_factor: Optional[float] = None
    is_active: Optional[bool] = None


class TechResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    color: str
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    start_address: Optional[str] = None
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None
    end_address: Optional[str] = None
    work_start_time: Optional[time] = None
    work_end_time: Optional[time] = None
    working_days: Optional[dict] = None
    max_stops_per_day: int
    efficiency_factor: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
