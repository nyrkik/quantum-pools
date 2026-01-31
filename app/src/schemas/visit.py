"""Visit and ChemicalReading schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date


class VisitCreate(BaseModel):
    property_id: str
    tech_id: Optional[str] = None
    scheduled_date: date
    service_day: Optional[str] = None
    notes: Optional[str] = None


class VisitUpdate(BaseModel):
    tech_id: Optional[str] = None
    scheduled_date: Optional[date] = None
    status: Optional[str] = None
    service_performed: Optional[str] = None
    notes: Optional[str] = None


class VisitCompleteRequest(BaseModel):
    service_performed: Optional[str] = None
    notes: Optional[str] = None
    duration_minutes: Optional[int] = None


class VisitResponse(BaseModel):
    id: str
    property_id: str
    tech_id: Optional[str] = None
    scheduled_date: date
    service_day: Optional[str] = None
    status: str
    actual_arrival: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    service_performed: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Joined fields
    property_address: Optional[str] = None
    tech_name: Optional[str] = None
    customer_name: Optional[str] = None

    model_config = {"from_attributes": True}


class ChemicalReadingCreate(BaseModel):
    property_id: str
    visit_id: Optional[str] = None
    ph: Optional[float] = None
    free_chlorine: Optional[float] = None
    total_chlorine: Optional[float] = None
    combined_chlorine: Optional[float] = None
    alkalinity: Optional[float] = None
    calcium_hardness: Optional[float] = None
    cyanuric_acid: Optional[float] = None
    tds: Optional[float] = None
    phosphates: Optional[float] = None
    salt: Optional[float] = None
    water_temp: Optional[float] = None
    notes: Optional[str] = None


class ChemicalReadingResponse(BaseModel):
    id: str
    property_id: str
    visit_id: Optional[str] = None
    ph: Optional[float] = None
    free_chlorine: Optional[float] = None
    total_chlorine: Optional[float] = None
    combined_chlorine: Optional[float] = None
    alkalinity: Optional[float] = None
    calcium_hardness: Optional[float] = None
    cyanuric_acid: Optional[float] = None
    tds: Optional[float] = None
    phosphates: Optional[float] = None
    salt: Optional[float] = None
    water_temp: Optional[float] = None
    recommendations: Optional[dict] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: Optional[str] = None
    duration_minutes: int = 30
    price: float = 0.0


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None


class ServiceResponse(BaseModel):
    id: str
    name: str
    category: Optional[str] = None
    duration_minutes: int
    price: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
