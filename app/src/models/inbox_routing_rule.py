"""Inbox routing rules — maps email addresses to visibility permissions or block rules."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class InboxRoutingRule(Base):
    __tablename__ = "inbox_routing_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    address_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="exact")  # exact, contains
    action: Mapped[str] = mapped_column(String(20), default="route")  # route, block
    match_field: Mapped[str] = mapped_column(String(10), default="to")  # to = match on delivered_to, from = match on sender
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    required_permission: Mapped[str | None] = mapped_column(String(80), nullable=True)  # permission slug, null = everyone
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
