"""Internal message reactions — per-user emoji reactions on InternalMessage rows.

One row per (message, user, emoji). A user can attach multiple different
emojis to the same message but each emoji can only be added once (unique
constraint). Toggle behavior: re-POSTing the same (user, emoji) removes it.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class InternalMessageReaction(Base):
    __tablename__ = "internal_message_reactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("internal_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Native-rendered emoji character, e.g. "👍". Store the grapheme, not
    # an emoji-mart shortname — renders identically everywhere without a
    # font lookup. 16 chars accommodates the longest ZWJ sequences.
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_imr_msg_user_emoji"),
        Index("ix_imr_message_id", "message_id"),
    )
