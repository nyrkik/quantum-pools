"""FeedbackItem — in-app user feedback with AI triage."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_name: Mapped[str | None] = mapped_column(String(200))

    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)  # bug, feature, question, ux_issue
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    screenshot_urls: Mapped[list | None] = mapped_column(JSON, default=list)
    page_url: Mapped[str | None] = mapped_column(String(500))
    browser_info: Mapped[str | None] = mapped_column(String(500))

    # AI analysis
    ai_classification: Mapped[dict | None] = mapped_column(JSON)
    ai_response: Mapped[str | None] = mapped_column(Text)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="new")  # new, triaged, in_progress, resolved, closed
    priority: Mapped[str | None] = mapped_column(String(20))  # critical, high, medium, low
    resolved_by: Mapped[str | None] = mapped_column(String(200))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization", lazy="noload")
    user = relationship("User", lazy="noload")
