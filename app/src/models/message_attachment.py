"""Message attachments — shared by internal messages and agent messages."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    __table_args__ = (
        Index("ix_message_attachments_source", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # internal_message, agent_message
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # NULL until message is sent
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # original filename
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)  # uuid.ext on disk
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes

    # Inline image support. Set when the MIME part has Content-Disposition: inline
    # AND a Content-ID header. The HTML body refs them via `cid:<content_id>`;
    # the API rewrites those to /api/v1/attachments/{id}/raw before serving so
    # the iframe loads them. Inline attachments are excluded from the user-facing
    # attachments grid (they're already shown in the body where intended).
    content_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_inline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
