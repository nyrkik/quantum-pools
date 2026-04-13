"""SuppressedEmailSender — org-wide list of senders that should never
trigger the 'Add Contact' prompt. Covers automated notification senders,
marketing emails, and other addresses that aren't real contacts.

Supports both exact addresses ('system@entrata.com') and domain patterns
('*@entrata.com'). The pattern is checked case-insensitively.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class SuppressedEmailSender(Base):
    __tablename__ = "suppressed_email_senders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Exact email or domain pattern: "system@entrata.com" or "*@entrata.com"
    email_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(50))  # billing, vendor, notification, personal, marketing, other, spam
    folder_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("inbox_folders.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
