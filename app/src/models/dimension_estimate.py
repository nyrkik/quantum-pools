"""DimensionEstimate model — tracks pool dimension estimates from multiple sources."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class DimensionEstimate(Base):
    __tablename__ = "dimension_estimates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    water_feature_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("water_features.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False)  # inspection, perimeter, measurement, satellite, manual
    estimated_sqft: Mapped[float | None] = mapped_column(Float)
    perimeter_ft: Mapped[float | None] = mapped_column(Float)
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    water_feature = relationship("WaterFeature", back_populates="dimension_estimates", lazy="noload")
    organization = relationship("Organization", lazy="noload")
    user = relationship("User", lazy="noload")
