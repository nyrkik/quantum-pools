"""Customer schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CustomerCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    company_name: Optional[str] = None
    customer_type: str = "residential"
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    service_frequency: Optional[str] = None
    preferred_day: Optional[str] = None
    billing_frequency: str = "monthly"
    monthly_rate: float = 0.0
    payment_method: Optional[str] = None
    payment_terms_days: int = 30
    difficulty_rating: int = 1
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    customer_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    service_frequency: Optional[str] = None
    preferred_day: Optional[str] = None
    billing_frequency: Optional[str] = None
    monthly_rate: Optional[float] = None
    payment_method: Optional[str] = None
    payment_terms_days: Optional[int] = None
    difficulty_rating: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    customer_type: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    service_frequency: Optional[str] = None
    preferred_day: Optional[str] = None
    billing_frequency: str
    monthly_rate: float
    payment_method: Optional[str] = None
    payment_terms_days: int
    balance: float
    difficulty_rating: int
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    property_count: int = 0

    model_config = {"from_attributes": True}
