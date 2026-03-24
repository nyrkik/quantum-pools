"""Organization model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip_code: Mapped[str | None] = mapped_column(String(20))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str | None] = mapped_column(String(20))  # hex color e.g. #1e40af
    tagline: Mapped[str | None] = mapped_column(String(255))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100))
    billing_email: Mapped[str | None] = mapped_column(String(255))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Agent configuration
    agent_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_from_email: Mapped[str | None] = mapped_column(String(255))
    agent_from_name: Mapped[str | None] = mapped_column(String(100))
    agent_tone_rules: Mapped[str | None] = mapped_column(Text)
    agent_signature: Mapped[str | None] = mapped_column(Text)
    agent_business_hours_start: Mapped[int | None] = mapped_column(Integer)  # 7 = 7 AM
    agent_business_hours_end: Mapped[int | None] = mapped_column(Integer)    # 20 = 8 PM
    agent_timezone: Mapped[str | None] = mapped_column(String(50))
    agent_service_area: Mapped[str | None] = mapped_column(Text)
    agent_approval_phones: Mapped[str | None] = mapped_column(Text)  # JSON: [{"phone": "+1...", "name": "Brian"}]

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    members = relationship("OrganizationUser", back_populates="organization", lazy="noload")
