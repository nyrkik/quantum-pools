"""Property model — service location with pool details."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Address
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(20), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geocode_provider: Mapped[str | None] = mapped_column(String(50))

    # Pool details
    pool_type: Mapped[str | None] = mapped_column(String(50))
    pool_gallons: Mapped[int | None] = mapped_column(Integer)
    pool_surface: Mapped[str | None] = mapped_column(String(50))
    has_spa: Mapped[bool] = mapped_column(Boolean, default=False)
    has_water_feature: Mapped[bool] = mapped_column(Boolean, default=False)

    # Equipment
    pump_type: Mapped[str | None] = mapped_column(String(100))
    filter_type: Mapped[str | None] = mapped_column(String(100))
    heater_type: Mapped[str | None] = mapped_column(String(100))
    chlorinator_type: Mapped[str | None] = mapped_column(String(100))
    automation_system: Mapped[str | None] = mapped_column(String(100))

    # Access
    gate_code: Mapped[str | None] = mapped_column(String(50))
    access_instructions: Mapped[str | None] = mapped_column(Text)
    dog_on_property: Mapped[bool] = mapped_column(Boolean, default=False)

    # Service
    estimated_service_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_locked_to_day: Mapped[bool] = mapped_column(Boolean, default=False)
    service_day_pattern: Mapped[str | None] = mapped_column(String(20))
    photos: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer = relationship("Customer", back_populates="properties", lazy="noload")
    visits = relationship("Visit", back_populates="property", lazy="noload")
    chemical_readings = relationship("ChemicalReading", back_populates="property", lazy="noload")

    @property
    def full_address(self) -> str:
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}"
