"""Pool measurement model — ground-truth dimensions from tech photos + Claude Vision."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class PoolMeasurement(Base):
    __tablename__ = "pool_measurements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    measured_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )

    # Dimensions
    length_ft: Mapped[float | None] = mapped_column(Float)
    width_ft: Mapped[float | None] = mapped_column(Float)
    depth_shallow_ft: Mapped[float | None] = mapped_column(Float)
    depth_deep_ft: Mapped[float | None] = mapped_column(Float)
    depth_avg_ft: Mapped[float | None] = mapped_column(Float)

    # Calculated
    calculated_sqft: Mapped[float | None] = mapped_column(Float)
    calculated_gallons: Mapped[int | None] = mapped_column(Integer)

    # Metadata
    pool_shape: Mapped[str | None] = mapped_column(String(50))
    scale_reference: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)

    # Photos
    photo_paths: Mapped[dict | None] = mapped_column(JSON)

    # Analysis
    raw_analysis: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    applied_to_property: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="measurements", lazy="noload")
    organization = relationship("Organization", lazy="noload")
    user = relationship("User", lazy="noload")
