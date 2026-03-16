"""Chemical cost profile — computed per-BOW monthly chemical costs."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class ChemicalCostProfile(Base):
    __tablename__ = "chemical_cost_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    body_of_water_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bodies_of_water.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Computed monthly costs
    sanitizer_cost: Mapped[float] = mapped_column(Float, default=0.0)
    acid_cost: Mapped[float] = mapped_column(Float, default=0.0)
    cya_cost: Mapped[float] = mapped_column(Float, default=0.0)
    salt_cost: Mapped[float] = mapped_column(Float, default=0.0)
    cell_cost: Mapped[float] = mapped_column(Float, default=0.0)  # SWG cell amortization
    insurance_cost: Mapped[float] = mapped_column(Float, default=0.0)  # phosphate remover, enzyme, algaecide
    total_monthly: Mapped[float] = mapped_column(Float, default=0.0)

    # Tracking
    source: Mapped[str] = mapped_column(String(20), default="computed")  # computed, user_override
    overrides: Mapped[dict | None] = mapped_column(JSON)  # {"sanitizer_cost": true} — which fields user manually set
    adjustments_applied: Mapped[dict | None] = mapped_column(JSON)  # {"canopy_bonus": 0.15, ...}
    last_computed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Per-field user overrides for usage rates (null = use default)
    sanitizer_usage_override_oz: Mapped[float | None] = mapped_column(Float)
    acid_usage_override_oz: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    body_of_water = relationship("BodyOfWater", back_populates="chemical_cost_profile", lazy="noload")
    organization = relationship("Organization", lazy="noload")
