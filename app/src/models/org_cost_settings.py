"""Organization cost settings for profitability analysis."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class OrgCostSettings(Base):
    __tablename__ = "org_cost_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    burdened_labor_rate: Mapped[float] = mapped_column(Float, default=35.0)
    vehicle_cost_per_mile: Mapped[float] = mapped_column(Float, default=0.655)
    chemical_cost_per_gallon: Mapped[float] = mapped_column(Float, default=3.50)
    monthly_overhead: Mapped[float] = mapped_column(Float, default=2000.0)
    target_margin_pct: Mapped[float] = mapped_column(Float, default=35.0)
    residential_overhead_per_account: Mapped[float] = mapped_column(Float, default=10.0)
    commercial_overhead_per_account: Mapped[float] = mapped_column(Float, default=45.0)
    avg_drive_minutes: Mapped[float] = mapped_column(Float, default=5.0)
    avg_drive_miles: Mapped[float] = mapped_column(Float, default=2.0)
    visits_per_month: Mapped[float] = mapped_column(Float, default=4.0)

    # Charge thresholds
    auto_approve_threshold: Mapped[float] = mapped_column(Float, default=75.0)
    separate_invoice_threshold: Mapped[float] = mapped_column(Float, default=200.0)
    require_photo_threshold: Mapped[float] = mapped_column(Float, default=50.0)

    # Parts markup
    default_parts_markup_pct: Mapped[float] = mapped_column(Float, default=25.0)

    # Billing frequency discounts
    semi_annual_discount_type: Mapped[str] = mapped_column(String(10), default="percent")
    semi_annual_discount_value: Mapped[float] = mapped_column(Float, default=5.0)
    annual_discount_type: Mapped[str] = mapped_column(String(10), default="percent")
    annual_discount_value: Mapped[float] = mapped_column(Float, default=10.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization", lazy="noload")
