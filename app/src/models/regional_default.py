"""Regional chemical usage defaults — per-region, per-sanitizer baseline costs and usage rates."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class RegionalDefault(Base):
    __tablename__ = "regional_defaults"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    region_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sanitizer_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Per-visit usage rates (per 10,000 gallons)
    sanitizer_usage_oz: Mapped[float] = mapped_column(Float, default=24.0)
    acid_usage_oz: Mapped[float] = mapped_column(Float, default=8.0)

    # Prices
    sanitizer_price_per_unit: Mapped[float | None] = mapped_column(Float)
    sanitizer_unit: Mapped[str | None] = mapped_column(String(20))  # gallon, bucket, lb, bag
    acid_price_per_gallon: Mapped[float] = mapped_column(Float, default=8.0)
    cya_price_per_lb: Mapped[float] = mapped_column(Float, default=4.50)
    salt_price_per_bag: Mapped[float] = mapped_column(Float, default=7.0)

    # Monthly amortized costs
    cya_usage_lb_per_month_per_10k: Mapped[float] = mapped_column(Float, default=0.0)  # 0 for established pools
    salt_bags_per_year_per_10k: Mapped[float] = mapped_column(Float, default=2.0)
    salt_cell_replacement_cost: Mapped[float] = mapped_column(Float, default=0.0)  # amortized monthly
    insurance_chemicals_monthly: Mapped[float] = mapped_column(Float, default=0.0)  # phosphate remover, enzyme, algaecide per 10k gal

    # Metadata
    source: Mapped[str | None] = mapped_column(String(20))  # ai_estimated, verified
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
