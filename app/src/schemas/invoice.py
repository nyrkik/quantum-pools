"""Invoice schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


class InvoiceLineItemCreate(BaseModel):
    service_id: Optional[str] = None
    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = 1.0
    unit_price: float = 0.0
    is_taxed: bool = False
    sort_order: int = 0


class InvoiceLineItemResponse(BaseModel):
    id: str
    invoice_id: str
    service_id: Optional[str] = None
    description: str
    quantity: float
    unit_price: float
    amount: float
    is_taxed: bool
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceCreate(BaseModel):
    customer_id: str
    subject: Optional[str] = None
    issue_date: date
    due_date: date
    discount: float = 0.0
    tax_rate: float = 0.0
    is_recurring: bool = False
    notes: Optional[str] = None
    line_items: list[InvoiceLineItemCreate] = []


class InvoiceUpdate(BaseModel):
    subject: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    discount: Optional[float] = None
    tax_rate: Optional[float] = None
    notes: Optional[str] = None
    line_items: Optional[list[InvoiceLineItemCreate]] = None


class InvoiceResponse(BaseModel):
    id: str
    organization_id: str
    customer_id: str
    invoice_number: str
    subject: Optional[str] = None
    status: str
    issue_date: date
    due_date: date
    paid_date: Optional[date] = None
    subtotal: float
    discount: float
    tax_rate: float
    tax_amount: float
    total: float
    amount_paid: float
    balance: float
    is_recurring: bool
    notes: Optional[str] = None
    pss_invoice_id: Optional[str] = None
    payment_token: str
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Populated by API
    customer_name: str = ""
    line_items: list[InvoiceLineItemResponse] = []

    model_config = {"from_attributes": True}


class InvoiceStatsResponse(BaseModel):
    total_outstanding: float
    total_overdue: float
    monthly_revenue: float
    invoice_count: int
    paid_count: int
    overdue_count: int
