"""EMD Equipment model — equipment data extracted from inspection PDFs."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey
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

    # Filter Pumps (up to 3)
    filter_pump_1_make: Mapped[str | None] = mapped_column(String(100))
    filter_pump_1_model: Mapped[str | None] = mapped_column(String(100))
    filter_pump_1_hp: Mapped[str | None] = mapped_column(String(50))
    filter_pump_2_make: Mapped[str | None] = mapped_column(String(100))
    filter_pump_2_model: Mapped[str | None] = mapped_column(String(100))
    filter_pump_2_hp: Mapped[str | None] = mapped_column(String(50))
    filter_pump_3_make: Mapped[str | None] = mapped_column(String(100))
    filter_pump_3_model: Mapped[str | None] = mapped_column(String(100))
    filter_pump_3_hp: Mapped[str | None] = mapped_column(String(50))

    # Jet Pump
    jet_pump_1_make: Mapped[str | None] = mapped_column(String(100))
    jet_pump_1_model: Mapped[str | None] = mapped_column(String(100))
    jet_pump_1_hp: Mapped[str | None] = mapped_column(String(50))

    # Structured pump fields (from form fields, not blob)
    rp_make: Mapped[str | None] = mapped_column(String(100))
    rp_model: Mapped[str | None] = mapped_column(String(100))
    rp_hp: Mapped[str | None] = mapped_column(String(50))
    bp_make: Mapped[str | None] = mapped_column(String(100))
    bp_model: Mapped[str | None] = mapped_column(String(100))
    bp_hp: Mapped[str | None] = mapped_column(String(50))

    # Filter
    filter_1_type: Mapped[str | None] = mapped_column(String(50))
    filter_1_make: Mapped[str | None] = mapped_column(String(100))
    filter_1_model: Mapped[str | None] = mapped_column(String(100))
    filter_1_capacity_gpm: Mapped[int | None] = mapped_column(Integer)
    filter_cleaning_method: Mapped[str | None] = mapped_column(String(100))

    # Diatomaceous filter
    df_type: Mapped[str | None] = mapped_column(String(50))
    df_make: Mapped[str | None] = mapped_column(String(100))

    # Sanitizer
    sanitizer_1_type: Mapped[str | None] = mapped_column(String(50))
    sanitizer_1_details: Mapped[str | None] = mapped_column(String(200))
    sanitizer_2_type: Mapped[str | None] = mapped_column(String(50))
    sanitizer_2_details: Mapped[str | None] = mapped_column(String(200))

    # Drains
    main_drain_type: Mapped[str | None] = mapped_column(String(100))
    main_drain_model: Mapped[str | None] = mapped_column(String(100))
    main_drain_install_date: Mapped[str | None] = mapped_column(String(50))
    main_drain_capacity_gpm: Mapped[int | None] = mapped_column(Integer)
    main_drain_config: Mapped[str | None] = mapped_column(String(50))
    equalizer_model: Mapped[str | None] = mapped_column(String(100))
    equalizer_install_date: Mapped[str | None] = mapped_column(String(50))
    equalizer_capacity_gpm: Mapped[int | None] = mapped_column(Integer)

    # Skimmers
    skimmer_count: Mapped[int | None] = mapped_column(Integer)

    # Equipment match
    equipment_matches_emd: Mapped[bool | None] = mapped_column(Boolean)

    # Raw equipment text blob (for reference/reparse)
    equipment_text: Mapped[str | None] = mapped_column(Text)

    # Notes
    pump_notes: Mapped[str | None] = mapped_column(Text)
    filter_notes: Mapped[str | None] = mapped_column(Text)
    sanitizer_notes: Mapped[str | None] = mapped_column(Text)
    main_drain_notes: Mapped[str | None] = mapped_column(Text)
    equalizer_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    inspection = relationship("EMDInspection", back_populates="equipment", lazy="noload")
    facility = relationship("EMDFacility", lazy="noload")
