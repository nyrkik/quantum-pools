"""EquipmentCatalog — shared canonical equipment reference."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class EquipmentCatalog(Base):
    __tablename__ = "equipment_catalog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    equipment_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), index=True)
    model_number: Mapped[str | None] = mapped_column(String(100), index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(String(500))
    specs: Mapped[dict | None] = mapped_column(JSON)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    is_common: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_by_org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    equipment_items = relationship("EquipmentItem", back_populates="catalog_equipment", lazy="noload")
    parts = relationship("PartsCatalog", back_populates="for_equipment", lazy="noload")
