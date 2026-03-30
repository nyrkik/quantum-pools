"""Pydantic schemas for agent action (job) endpoints."""

from pydantic import BaseModel
from typing import Optional


class LineItemBody(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0


class CreateActionBody(BaseModel):
    agent_message_id: Optional[str] = None
    action_type: str
    description: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    customer_name: Optional[str] = None
    property_address: Optional[str] = None
    job_path: str = "internal"  # "internal" or "customer"
    line_items: Optional[list[LineItemBody]] = None  # for customer path


class UpdateActionBody(BaseModel):
    status: Optional[str] = None
    action_type: Optional[str] = None
    assigned_to: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    invoice_id: Optional[str] = None


class AddCommentBody(BaseModel):
    text: str


class CreateTaskBody(BaseModel):
    title: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class UpdateTaskBody(BaseModel):
    title: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None
