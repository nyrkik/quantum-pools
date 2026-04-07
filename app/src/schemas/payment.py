"""Payment schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


class PaymentCreate(BaseModel):
    customer_id: Optional[str] = None
    invoice_id: Optional[str] = None
    amount: float = Field(..., gt=0)
    payment_method: str = Field(..., pattern="^(cash|check|credit_card|card|ach|stripe|other)$")
    payment_date: date
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: str
    organization_id: str
    customer_id: Optional[str] = None
    invoice_id: Optional[str] = None
    amount: float
    payment_method: str
    payment_date: date
    status: str
    stripe_payment_intent_id: Optional[str] = None
    stripe_charge_id: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Populated by API
    customer_name: str = ""
    invoice_number: Optional[str] = None

    model_config = {"from_attributes": True}
