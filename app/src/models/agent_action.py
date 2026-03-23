"""Agent action items — follow-ups, bids, callbacks extracted from email responses."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_message_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_messages.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(50))  # follow_up, bid, schedule_change, site_visit, callback, other
    description: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(String(100))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, in_progress, done, cancelled
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message = relationship("AgentMessage", backref="actions")
