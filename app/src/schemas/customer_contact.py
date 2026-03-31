"""Pydantic schemas for CustomerContact CRUD."""

from typing import Optional
from pydantic import BaseModel


class ContactCreate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    receives_estimates: bool = False
    receives_invoices: bool = False
    receives_service_updates: bool = False
    is_primary: bool = False
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    receives_estimates: Optional[bool] = None
    receives_invoices: Optional[bool] = None
    receives_service_updates: Optional[bool] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None
