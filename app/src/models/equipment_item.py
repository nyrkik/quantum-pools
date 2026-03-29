"""EquipmentItem — structured equipment per water feature."""

import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, Boolean, DateTime, Date, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class EquipmentItem(Base):
    __tablename__ = "equipment_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    water_feature_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("water_features.id", ondelete="CASCADE"), nullable=False, index=True
    )

    equipment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    part_number: Mapped[str | None] = mapped_column(String(100))
    normalized_name: Mapped[str | None] = mapped_column(String(200), index=True)
    horsepower: Mapped[float | None] = mapped_column(Float)
    flow_rate_gpm: Mapped[int | None] = mapped_column(Integer)
    voltage: Mapped[int | None] = mapped_column(Integer)
    catalog_part_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("parts_catalog.id", ondelete="SET NULL")
    )
    install_date: Mapped[date | None] = mapped_column(Date)
    warranty_expires: Mapped[date | None] = mapped_column(Date)
    expected_lifespan_years: Mapped[int | None] = mapped_column(Integer)
    system_group: Mapped[str | None] = mapped_column(String(50))
    catalog_equipment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("equipment_catalog.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    replaced_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("equipment_items.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization", lazy="noload")
    water_feature = relationship("WaterFeature", lazy="noload")
    catalog_part = relationship("PartsCatalog", lazy="noload")
    replaced_by = relationship("EquipmentItem", remote_side="EquipmentItem.id", lazy="noload")
    catalog_equipment = relationship("EquipmentCatalog", back_populates="equipment_items", lazy="noload")
    events = relationship("EquipmentEvent", back_populates="equipment_item", lazy="noload")
