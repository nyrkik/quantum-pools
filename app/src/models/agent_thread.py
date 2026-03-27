"""Agent conversation threads — groups related emails into conversations."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class AgentThread(Base):
    __tablename__ = "agent_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)  # normalized_subject|contact_email
    contact_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))  # original subject from first message
    matched_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"))
    customer_name: Mapped[str | None] = mapped_column(String(200))
    property_address: Mapped[str | None] = mapped_column(String(300))

    # Denormalized thread-level status (updated on each message add/status change)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, handled, ignored
    urgency: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(50))
    message_count: Mapped[int] = mapped_column(Integer, default=1)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_direction: Mapped[str] = mapped_column(String(10), default="inbound")
    last_snippet: Mapped[str | None] = mapped_column(String(200))
    has_pending: Mapped[bool] = mapped_column(Boolean, default=True)
    has_open_actions: Mapped[bool] = mapped_column(Boolean, default=False)

    # Inbox routing / visibility
    visibility_permission: Mapped[str | None] = mapped_column(String(80), nullable=True)  # permission slug required to view (null = everyone)
    delivered_to: Mapped[str | None] = mapped_column(String(255), nullable=True)  # org address that received the email
    routing_rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("inbox_routing_rules.id"), nullable=True)

    # Thread assignment
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages = relationship("AgentMessage", back_populates="thread", order_by="AgentMessage.received_at")
