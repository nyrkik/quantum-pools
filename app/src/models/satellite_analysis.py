"""Satellite analysis model — cached pool detection and vegetation analysis results."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class SatelliteAnalysis(Base):
    __tablename__ = "satellite_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body_of_water_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bodies_of_water.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )

    # Pool detection
    pool_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_pool_sqft: Mapped[float | None] = mapped_column(Float)
    pool_contour_points: Mapped[dict | None] = mapped_column(JSON)
    pool_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Vegetation analysis
    vegetation_pct: Mapped[float] = mapped_column(Float, default=0.0)
    canopy_overhang_pct: Mapped[float] = mapped_column(Float, default=0.0)
    hardscape_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Shadow analysis
    shadow_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # User-placed pin coordinates (override geocode center)
    pool_lat: Mapped[float | None] = mapped_column(Float)
    pool_lng: Mapped[float | None] = mapped_column(Float)

    # Image data
    image_url: Mapped[str | None] = mapped_column(Text)
    image_zoom: Mapped[int] = mapped_column(default=20)
    image_width: Mapped[int] = mapped_column(default=640)
    image_height: Mapped[int] = mapped_column(default=640)

    # Metadata
    analysis_version: Mapped[str] = mapped_column(String(20), default="1.0")
    raw_results: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="satellite_analyses", lazy="noload")
    body_of_water = relationship("BodyOfWater", back_populates="satellite_analysis", lazy="noload")
    organization = relationship("Organization", lazy="noload")
