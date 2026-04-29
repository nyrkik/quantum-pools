"""Customer model."""

import uuid
import enum
from datetime import datetime, date, timezone
from sqlalchemy import String, Boolean, DateTime, Date, Text, Integer, Float, ForeignKey, Enum, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class CustomerStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    pending = "pending"
    one_time = "one_time"  # legacy — use service_call
    service_call = "service_call"
    lead = "lead"


class CustomerType(str, enum.Enum):
    residential = "residential"
    commercial = "commercial"


class BillingFrequency(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


from src.core.enums import PaymentMethod  # noqa: F401 — re-exported for backward compat


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    customer_type: Mapped[str] = mapped_column(String(20), default=CustomerType.residential.value)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    billing_address: Mapped[str | None] = mapped_column(Text)
    billing_city: Mapped[str | None] = mapped_column(String(100))
    billing_state: Mapped[str | None] = mapped_column(String(50))
    billing_zip: Mapped[str | None] = mapped_column(String(20))
    service_frequency: Mapped[str | None] = mapped_column(String(50))
    preferred_day: Mapped[str | None] = mapped_column(String(100))
    billing_frequency: Mapped[str] = mapped_column(String(20), default=BillingFrequency.monthly.value)
    monthly_rate: Mapped[float] = mapped_column(Float, default=0.0)
    payment_method: Mapped[str | None] = mapped_column(String(20))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty_rating: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(Text)

    # PSS migration + billing
    pss_id: Mapped[str | None] = mapped_column(String(50), index=True)
    autopay_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))

    # Billing cycle tracking
    billing_day_of_month: Mapped[int] = mapped_column(Integer, default=1)  # 1-28
    next_billing_date: Mapped[date | None] = mapped_column(Date)
    last_billed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Saved payment method (Stripe)
    stripe_payment_method_id: Mapped[str | None] = mapped_column(String(255))
    stripe_card_last4: Mapped[str | None] = mapped_column(String(4))
    stripe_card_brand: Mapped[str | None] = mapped_column(String(20))
    stripe_card_exp_month: Mapped[int | None] = mapped_column(Integer)
    stripe_card_exp_year: Mapped[int | None] = mapped_column(Integer)

    # Card setup token (public link for customer to save card)
    card_setup_token: Mapped[str | None] = mapped_column(String(64), unique=True)

    # Dunning
    autopay_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    autopay_last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phase 8 — per-customer override of org late-fee policy. NULL means
    # "inherit from org"; True/False forces on/off regardless of org config.
    # Used for negotiated commercial accounts that should never receive a
    # late fee even if the org enables it generally.
    late_fee_override_enabled: Mapped[bool | None] = mapped_column(Boolean)

    # Computed display name — single source of truth for all queries
    display_name_col: Mapped[str | None] = mapped_column("display_name", String(200), index=True)

    status: Mapped[str] = mapped_column(String(20), default=CustomerStatus.active.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization", lazy="noload")
    properties = relationship("Property", back_populates="customer", lazy="noload")
    invoices = relationship("Invoice", back_populates="customer", lazy="noload")
    payments = relationship("Payment", back_populates="customer", lazy="noload")

    @property
    def has_payment_method(self) -> bool:
        return bool(self.stripe_payment_method_id)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        if self.customer_type == "commercial":
            return self.first_name
        return self.full_name.strip()

    def _compute_display_name(self) -> str:
        if self.customer_type == "commercial":
            return self.first_name.strip()
        return f"{self.first_name} {self.last_name}".strip()


@event.listens_for(Customer, "before_insert")
@event.listens_for(Customer, "before_update")
def _set_display_name(mapper, connection, target):
    target.display_name_col = target._compute_display_name()
