"""EMD Equipment model — equipment data extracted from inspection PDFs."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class EMDEquipment(Base):
    __tablename__ = "emd_equipment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emd_inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emd_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Pool specs
    pool_capacity_gallons: Mapped[int | None] = mapped_column(Integer)
    flow_rate_gpm: Mapped[int | None] = mapped_column(Integer)

    # Pumps
    filter_pump_1_make: Mapped[str | None] = mapped_column(String(100))
    filter_pump_1_model: Mapped[str | None] = mapped_column(String(100))
    filter_pump_1_hp: Mapped[str | None] = mapped_column(String(50))

    # Filter
    filter_1_type: Mapped[str | None] = mapped_column(String(50))
    filter_1_make: Mapped[str | None] = mapped_column(String(100))
    filter_1_model: Mapped[str | None] = mapped_column(String(100))

    # Sanitizer
    sanitizer_1_type: Mapped[str | None] = mapped_column(String(50))
    sanitizer_1_details: Mapped[str | None] = mapped_column(String(200))

    # Drains
    main_drain_type: Mapped[str | None] = mapped_column(String(100))
    main_drain_model: Mapped[str | None] = mapped_column(String(100))
    main_drain_install_date: Mapped[str | None] = mapped_column(String(50))
    equalizer_model: Mapped[str | None] = mapped_column(String(100))
    equalizer_install_date: Mapped[str | None] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    inspection = relationship("EMDInspection", back_populates="equipment", lazy="noload")
    facility = relationship("EMDFacility", lazy="noload")
