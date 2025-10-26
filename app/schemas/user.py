"""
User Pydantic schemas for profile management.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    """Base user schema with common fields."""

    email: EmailStr = Field(..., description="User email address")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    last_name: Optional[str] = Field(None, max_length=100, description="Last name")
    timezone: Optional[str] = Field(None, max_length=50, description="User timezone (e.g., 'America/Los_Angeles')")
    locale: str = Field(default='en_US', max_length=10, description="User locale (e.g., 'en_US')")

    @field_validator('email')
    @classmethod
    def email_to_lowercase(cls, v: str) -> str:
        """Convert email to lowercase."""
        return v.lower()


class UserCreate(UserBase):
    """Schema for creating a new user (internal use)."""

    password: str = Field(..., min_length=8, max_length=100, description="User password")


class UserUpdate(BaseModel):
    """Schema for updating user profile (all fields optional)."""

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    locale: Optional[str] = Field(None, max_length=10)


class UserResponse(UserBase):
    """Schema for user responses (includes database fields)."""

    id: UUID
    is_active: bool
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    login_count: int = 0
    created_at: datetime
    updated_at: datetime
    full_name: str = Field(..., description="Computed full name")

    model_config = ConfigDict(from_attributes=True)


class UserWithOrganizations(UserResponse):
    """Schema for user with their organizations."""

    organizations: list["OrganizationMembership"] = Field(default_factory=list, description="User's organizations")

    model_config = ConfigDict(from_attributes=True)


class OrganizationMembership(BaseModel):
    """User's membership in an organization."""

    organization_id: UUID
    organization_name: str
    organization_slug: str
    role: str = Field(..., description="User's role: owner, admin, manager, technician, readonly")
    is_primary_org: bool = Field(default=False, description="Whether this is the user's primary organization")
    joined_at: datetime = Field(..., description="When user joined this organization")

    model_config = ConfigDict(from_attributes=True)
