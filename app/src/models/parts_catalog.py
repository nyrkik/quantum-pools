"""PartsCatalog — shared scraped product database (no org_id)."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, JSON, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class PartsCatalog(Base):
    __tablename__ = "parts_catalog"
    __table_args__ = (
        UniqueConstraint("vendor_provider", "sku", name="uq_parts_catalog_vendor_sku"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    subcategory: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    product_url: Mapped[str | None] = mapped_column(String(500))
    specs: Mapped[dict | None] = mapped_column(JSON)
    compatible_with: Mapped[dict | None] = mapped_column(JSON)
    for_equipment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("equipment_catalog.id", ondelete="SET NULL")
    )
    is_chemical: Mapped[bool] = mapped_column(Boolean, default=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    for_equipment = relationship("EquipmentCatalog", back_populates="parts", lazy="noload")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
