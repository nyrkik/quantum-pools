"""BodyOfWater model — individual body of water (pool, spa, fountain) within a property."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class BodyOfWater(Base):
    __tablename__ = "bodies_of_water"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Identity
    name: Mapped[str | None] = mapped_column(String(100))
    water_type: Mapped[str] = mapped_column(String(20), nullable=False, default="pool")
    # Pool details
    pool_type: Mapped[str | None] = mapped_column(String(50))
    pool_gallons: Mapped[int | None] = mapped_column(Integer)
    pool_sqft: Mapped[float | None] = mapped_column(Float)
    pool_surface: Mapped[str | None] = mapped_column(String(50))
    pool_length_ft: Mapped[float | None] = mapped_column(Float)
    pool_width_ft: Mapped[float | None] = mapped_column(Float)
    pool_depth_shallow: Mapped[float | None] = mapped_column(Float)
    pool_depth_deep: Mapped[float | None] = mapped_column(Float)
    pool_depth_avg: Mapped[float | None] = mapped_column(Float)
    pool_shape: Mapped[str | None] = mapped_column(String(50))
    pool_volume_method: Mapped[str | None] = mapped_column(String(20))

    # Shape & structure details
    has_rounded_corners: Mapped[bool] = mapped_column(Boolean, default=False)
    step_entry_count: Mapped[int] = mapped_column(Integer, default=0)
    has_bench_shelf: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dimension tracking
    dimension_source: Mapped[str | None] = mapped_column(String(20))  # inspection, perimeter, measurement, satellite, manual
    dimension_source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    perimeter_ft: Mapped[float | None] = mapped_column(Float)

    # Sanitizer / chemical method
    sanitizer_type: Mapped[str | None] = mapped_column(String(50))  # tabs, liquid, salt, trichlor, dichlor, cal_hypo

    # Equipment
    pump_type: Mapped[str | None] = mapped_column(String(100))
    filter_type: Mapped[str | None] = mapped_column(String(100))
    heater_type: Mapped[str | None] = mapped_column(String(100))
    chlorinator_type: Mapped[str | None] = mapped_column(String(100))
    automation_system: Mapped[str | None] = mapped_column(String(100))

    # Infrastructure
    fill_method: Mapped[str | None] = mapped_column(String(50))  # tap, ro_system, truck, recycled
    drain_type: Mapped[str | None] = mapped_column(String(50))  # main_drain, surge, circulation
    drain_method: Mapped[str | None] = mapped_column(String(50))  # sewer, catch_basin, storm_drain
    drain_count: Mapped[int | None] = mapped_column(Integer)
    drain_cover_compliant: Mapped[bool | None] = mapped_column(Boolean)  # VGB/anti-vortex
    drain_cover_install_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drain_cover_expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    equalizer_cover_compliant: Mapped[bool | None] = mapped_column(Boolean)
    equalizer_cover_install_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    equalizer_cover_expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plumbing_size_inches: Mapped[float | None] = mapped_column(Float)
    pool_cover_type: Mapped[str | None] = mapped_column(String(50))  # automatic, manual, safety_net, none
    turnover_hours: Mapped[float | None] = mapped_column(Float)
    skimmer_count: Mapped[int | None] = mapped_column(Integer)
    equipment_year: Mapped[int | None] = mapped_column(Integer)
    equipment_pad_location: Mapped[str | None] = mapped_column(String(100))

    # Service
    estimated_service_minutes: Mapped[int] = mapped_column(Integer, default=30)
    monthly_rate: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="bodies_of_water", lazy="noload")
    organization = relationship("Organization", lazy="noload")
    difficulty = relationship("PropertyDifficulty", back_populates="body_of_water", uselist=False, lazy="noload")
    jurisdiction = relationship("PropertyJurisdiction", back_populates="body_of_water", uselist=False, lazy="noload")
    measurements = relationship("PoolMeasurement", back_populates="body_of_water", lazy="noload")
    chemical_readings = relationship("ChemicalReading", back_populates="body_of_water", lazy="noload")
    satellite_analysis = relationship("SatelliteAnalysis", back_populates="body_of_water", uselist=False, lazy="noload")
    dimension_estimates = relationship("DimensionEstimate", back_populates="body_of_water", lazy="noload")
    chemical_cost_profile = relationship("ChemicalCostProfile", back_populates="body_of_water", uselist=False, lazy="noload")
