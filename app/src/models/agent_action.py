"""Agent action items — follow-ups, bids, callbacks extracted from email responses."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_message_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_messages.id"), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_threads.id"), index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    # For standalone actions (not from email)
    customer_name: Mapped[str | None] = mapped_column(String(200))
    property_address: Mapped[str | None] = mapped_column(String(300))
    action_type: Mapped[str] = mapped_column(String(50))  # follow_up, bid, schedule_change, site_visit, callback, other
    description: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(String(100))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, in_progress, done, suggested, cancelled
    created_by: Mapped[str | None] = mapped_column(String(100))  # user name or "DeepBlue"
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message = relationship("AgentMessage", backref="actions")
    comments = relationship("AgentActionComment", back_populates="action", order_by="AgentActionComment.created_at")


class AgentActionComment(Base):
    __tablename__ = "agent_action_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_actions.id"), index=True)
    author: Mapped[str] = mapped_column(String(100))  # user name
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    action = relationship("AgentAction", back_populates="comments")
