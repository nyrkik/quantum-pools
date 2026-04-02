"""Internal messaging — team-to-team chat with work context."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, JSON, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class InternalThread(Base):
    __tablename__ = "internal_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Participants as JSON array of user_ids
    participant_ids: Mapped[list] = mapped_column(JSON, default=list)

    # Optional work context links
    customer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    property_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="SET NULL")
    )
    action_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="SET NULL")
    )

    case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("service_cases.id", ondelete="SET NULL"), index=True
    )

    # Thread metadata
    subject: Mapped[str | None] = mapped_column(String(200))
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # normal, urgent
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, acknowledged, completed, archived
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_by: Mapped[str | None] = mapped_column(String(36))

    # Acknowledge/complete tracking
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(36))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(String(36))

    # Convert to job
    converted_to_action_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="SET NULL")
    )

    # Escalation tracking
    escalation_level: Mapped[int] = mapped_column(Integer, default=1)  # 1=in-app, 2=push, 3=email

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    case = relationship("ServiceCase", back_populates="internal_threads")
    messages = relationship("InternalMessage", back_populates="thread", order_by="InternalMessage.created_at", lazy="noload")
    customer = relationship("Customer", lazy="noload")


class InternalMessage(Base):
    __tablename__ = "internal_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("internal_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    thread = relationship("InternalThread", back_populates="messages", lazy="noload")
    from_user = relationship("User", lazy="noload")
