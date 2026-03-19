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
