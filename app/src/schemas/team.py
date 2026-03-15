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
    role: str
    is_developer: bool
    is_active: bool
    created_at: datetime


class TeamMemberUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class TeamDeveloperToggle(BaseModel):
    is_developer: bool


class TeamInviteRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="readonly")
    password: str = Field(..., min_length=8, max_length=128)
