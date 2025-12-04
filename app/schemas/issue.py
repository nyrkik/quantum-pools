"""
Pydantic schemas for Issue model.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class IssueBase(BaseModel):
    """Base issue schema with common fields."""
    customer_id: UUID
    description: str = Field(..., min_length=1, max_length=2000)
    severity: str = "medium"  # low, medium, high, critical
    photos: Optional[List[str]] = None


class IssueCreate(IssueBase):
    """Schema for creating a new issue."""
    visit_id: Optional[UUID] = None  # Optional link to a visit


class IssueUpdate(BaseModel):
    """Schema for updating an issue (all fields optional)."""
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    severity: Optional[str] = None
    photos: Optional[List[str]] = None
    status: Optional[str] = None
    assigned_tech_id: Optional[UUID] = None
    scheduled_date: Optional[datetime] = None
    resolution_notes: Optional[str] = None


class IssueResponse(IssueBase):
    """Schema for issue response."""
    id: UUID
    organization_id: UUID
    visit_id: Optional[UUID] = None
    reported_by_tech_id: UUID
    reported_at: datetime
    status: str  # pending, scheduled, in_progress, resolved, closed
    assigned_tech_id: Optional[UUID] = None
    scheduled_date: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by_tech_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Related data
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    reported_by_name: Optional[str] = None
    assigned_tech_name: Optional[str] = None
    resolved_by_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IssueListResponse(BaseModel):
    """Schema for list of issues."""
    issues: List[IssueResponse]
    total: int
