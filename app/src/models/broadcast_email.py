"""Broadcast email — bulk sends to filtered customer lists."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class BroadcastEmail(Base):
    __tablename__ = "broadcast_emails"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Filter: all_active, commercial, residential, or JSON list of customer_ids
    filter_type: Mapped[str] = mapped_column(String(50), nullable=False, default="all_active")
    filter_data: Mapped[str | None] = mapped_column(Text)  # JSON for custom filters

    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    # queued → sending → completed | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")

    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
