"""Customer model."""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer, Float, ForeignKey, Enum, event
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


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    check = "check"
    credit_card = "credit_card"
    ach = "ach"
    other = "other"


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
