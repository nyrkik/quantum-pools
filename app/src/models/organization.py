"""Organization model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey
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

    # Inbound email configuration
    inbound_email_address: Mapped[str | None] = mapped_column(String(255))  # e.g. inbox-sapphire@mail.quantumpoolspro.com
    inbound_email_provider: Mapped[str | None] = mapped_column(String(50))  # imap, sendgrid, postmark, mailgun
    imap_host: Mapped[str | None] = mapped_column(String(255))
    imap_user: Mapped[str | None] = mapped_column(String(255))
    imap_password_encrypted: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted — NOT YET IMPLEMENTED

    # Billing contact — who manages subscription/payments (separate from permissions)
    billing_contact_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # Structured addresses: {mailing: {street, city, state, zip}, physical: {same_as: "mailing"} | {street...}, billing: {same_as: "mailing"} | {street...}}
    addresses: Mapped[str | None] = mapped_column(Text)

    # DeepBlue quotas — per-user and per-org caps (defaults set in migration)
    deepblue_user_daily_input_tokens: Mapped[int] = mapped_column(Integer, default=500000)
    deepblue_user_daily_output_tokens: Mapped[int] = mapped_column(Integer, default=100000)
    deepblue_user_monthly_input_tokens: Mapped[int] = mapped_column(Integer, default=5000000)
    deepblue_user_monthly_output_tokens: Mapped[int] = mapped_column(Integer, default=1000000)
    deepblue_org_monthly_input_tokens: Mapped[int] = mapped_column(Integer, default=50000000)
    deepblue_org_monthly_output_tokens: Mapped[int] = mapped_column(Integer, default=10000000)
    deepblue_rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30)

    # Contact learning — show modal/banner for unknown email senders
    email_contact_learning: Mapped[bool] = mapped_column(Boolean, default=True)

    # platform_events retention — how long this org's events stick
    # before the daily retention-purge job deletes them. Sapphire
    # (dogfood) defaults to 10 years; paying orgs default to 3 years
    # via migration. Read by `retention_purge.purge_expired_events`.
    event_retention_days: Mapped[int] = mapped_column(Integer, default=1095)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    members = relationship("OrganizationUser", back_populates="organization", lazy="noload")
