"""Pydantic schemas for team management."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class TeamMemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: str
    is_developer: bool
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class TeamMemberUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class TeamDeveloperToggle(BaseModel):
    is_developer: bool


class TeamInviteRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="readonly")
    phone: Optional[str] = None
