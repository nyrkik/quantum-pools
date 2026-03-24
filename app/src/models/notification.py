"""In-app notifications."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # action_comment, action_assigned, message_pending
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))  # e.g. /inbox (action tab)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
