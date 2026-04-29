"""Customer schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


class CustomerCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field("", max_length=100)
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
    status: str = "active"
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
    payment_method: Optional[str] = None
    payment_terms_days: Optional[int] = None
    difficulty_rating: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    autopay_enabled: Optional[bool] = None
    billing_day_of_month: Optional[int] = None
    late_fee_override_enabled: Optional[bool] = None


class CustomerResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    display_name: Optional[str] = None
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
    status: str
    notes: Optional[str] = None
    is_active: bool
    autopay_enabled: bool = False
    billing_day_of_month: int = 1
    next_billing_date: Optional[date] = None
    has_payment_method: bool = False
    stripe_card_last4: Optional[str] = None
    stripe_card_brand: Optional[str] = None
    stripe_card_exp_month: Optional[int] = None
    stripe_card_exp_year: Optional[int] = None
    autopay_failure_count: int = 0
    late_fee_override_enabled: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    property_count: int = 0
    first_property_id: Optional[str] = None
    first_property_address: Optional[str] = None
    first_property_pool_type: Optional[str] = None
    wf_summary: Optional[str] = None

    model_config = {"from_attributes": True}


class CustomerCreateWithProperty(CustomerCreate):
    """Create customer + property + primary WF in one call."""
    address: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    zip_code: str = Field(..., min_length=1)
    gate_code: Optional[str] = None
    access_instructions: Optional[str] = None
    dog_on_property: bool = False
    water_type: str = "pool"
    pool_type: Optional[str] = None
