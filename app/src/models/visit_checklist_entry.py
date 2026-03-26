"""VisitChecklistEntry model — records which checklist items were completed during a visit."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class VisitChecklistEntry(Base):
    __tablename__ = "visit_checklist_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    visit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checklist_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("service_checklist_items.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # denormalized
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    visit = relationship("Visit", back_populates="checklist_entries", lazy="noload")
    checklist_item = relationship("ServiceChecklistItem", lazy="noload")
