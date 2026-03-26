"""EquipmentEvent — replacement/repair history for equipment items."""

import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class EquipmentEvent(Base):
    __tablename__ = "equipment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("equipment_items.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    part_purchase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("part_purchases.id", ondelete="SET NULL")
    )
    performed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", lazy="noload")
    equipment_item = relationship("EquipmentItem", back_populates="events", lazy="noload")
    part_purchase = relationship("PartPurchase", lazy="noload")
    performer = relationship("User", lazy="noload")
