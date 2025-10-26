"""
Organization database model.
Stores organization/tenant information for multi-tenancy.
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Organization(Base):
    """Organization model for multi-tenant SaaS."""

    __tablename__ = "organizations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Basic information
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    subdomain = Column(String(63), unique=True)

    # Subscription
    plan_tier = Column(String(50), nullable=False, default='starter')
    subscription_status = Column(String(50), nullable=False, default='trial')
    trial_ends_at = Column(DateTime)
    trial_days = Column(Integer, default=14)

    # Billing
    billing_email = Column(String(255))
    billing_address = Column(String)
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))

    # Plan limits
    max_users = Column(Integer)
    max_customers = Column(Integer)
    max_techs = Column(Integer)
    max_routes_per_day = Column(Integer)

    # Features
    features_enabled = Column(JSONB, default={})

    # Map provider
    default_map_provider = Column(String(50), default='openstreetmap')
    google_maps_api_key = Column(String(200))

    # Customization
    logo_url = Column(String(500))
    primary_color = Column(String(7))
    timezone = Column(String(50), default='America/Los_Angeles')

    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    onboarded_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customers = relationship("Customer", back_populates="organization")
    techs = relationship("Tech", back_populates="organization")
    routes = relationship("Route", back_populates="organization")
    organization_users = relationship("OrganizationUser", back_populates="organization")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}', slug='{self.slug}')>"
