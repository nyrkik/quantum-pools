"""
Organization Pydantic schemas for organization management.
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class OrganizationBase(BaseModel):
    """Base organization schema with common fields."""

    name: str = Field(..., min_length=1, max_length=200, description="Organization name")
    slug: Optional[str] = Field(None, min_length=3, max_length=100, pattern="^[a-z0-9-]+$", description="URL-friendly slug")
    subdomain: Optional[str] = Field(None, max_length=63, pattern="^[a-z0-9-]+$", description="Subdomain")
    timezone: str = Field(default='America/Los_Angeles', max_length=50, description="Organization timezone")
    default_map_provider: str = Field(
        default='openstreetmap',
        pattern="^(openstreetmap|google)$",
        description="Map provider: openstreetmap or google"
    )
    google_maps_api_key: Optional[str] = Field(None, max_length=200, description="Google Maps API key (if using Google)")


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""
    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    subdomain: Optional[str] = Field(None, max_length=63, pattern="^[a-z0-9-]+$")
    timezone: Optional[str] = Field(None, max_length=50)
    default_map_provider: Optional[str] = Field(None, pattern="^(openstreetmap|google)$")
    google_maps_api_key: Optional[str] = Field(None, max_length=200)
    logo_url: Optional[str] = Field(None, max_length=500)
    primary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", description="Hex color code")
    billing_email: Optional[str] = Field(None, max_length=255)
    billing_address: Optional[str] = None


class OrganizationResponse(OrganizationBase):
    """Schema for organization responses (includes database fields)."""

    id: UUID
    slug: str  # Override to make required
    plan_tier: str = Field(..., description="Subscription plan: starter, professional, enterprise")
    subscription_status: str = Field(..., description="Subscription status: trial, active, past_due, canceled")
    trial_ends_at: Optional[datetime] = None
    trial_days: int = 14
    max_users: Optional[int] = None
    max_customers: Optional[int] = None
    max_techs: Optional[int] = None
    features_enabled: dict[str, Any] = Field(default_factory=dict, description="Feature flags")
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    is_active: bool = True
    onboarded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationWithStats(OrganizationResponse):
    """Organization with usage statistics."""

    total_users: int = 0
    total_customers: int = 0
    total_drivers: int = 0
    total_routes: int = 0

    model_config = ConfigDict(from_attributes=True)


class OrganizationUserResponse(BaseModel):
    """Schema for organization user membership."""

    id: UUID
    user_id: UUID
    organization_id: UUID
    role: str = Field(..., pattern="^(owner|admin|manager|technician|readonly)$", description="User role")
    is_primary_org: bool = False
    invitation_accepted_at: Optional[datetime] = None
    created_at: datetime

    # User info
    user_email: str
    user_first_name: str
    user_last_name: Optional[str] = None
    user_full_name: str

    model_config = ConfigDict(from_attributes=True)


class InviteUserRequest(BaseModel):
    """Schema for inviting a user to an organization."""

    email: str = Field(..., max_length=255, description="Email address to invite")
    role: str = Field(
        ...,
        pattern="^(admin|manager|technician|readonly)$",
        description="Role to assign (cannot invite as owner)"
    )

    @field_validator('email')
    @classmethod
    def email_to_lowercase(cls, v: str) -> str:
        """Convert email to lowercase."""
        return v.lower()


class UpdateUserRoleRequest(BaseModel):
    """Schema for updating a user's role in an organization."""

    role: str = Field(
        ...,
        pattern="^(owner|admin|manager|technician|readonly)$",
        description="New role to assign"
    )
