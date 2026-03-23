"""Agent message log — tracks all client emails and agent responses."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email_uid: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    direction: Mapped[str] = mapped_column(String(10))  # inbound, outbound
    from_email: Mapped[str] = mapped_column(String(255))
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))  # schedule, complaint, billing, gate_code, general, spam
    urgency: Mapped[str | None] = mapped_column(String(20))  # low, medium, high
    draft_response: Mapped[str | None] = mapped_column(Text)
    final_response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, sent, auto_sent, rejected, ignored
    approved_by: Mapped[str | None] = mapped_column(String(50))  # phone number or name
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matched_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    match_method: Mapped[str | None] = mapped_column(String(30))  # email, domain, company_name, sender_name, manual
    customer_name: Mapped[str | None] = mapped_column(String(200))
    property_address: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
