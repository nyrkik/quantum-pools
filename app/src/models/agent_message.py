"""Agent message log — tracks all client emails and agent responses."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email_uid: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    direction: Mapped[str] = mapped_column(String(10))  # inbound, outbound
    from_email: Mapped[str] = mapped_column(String(255))
    # Display name parsed from the raw From header at ingest. Null for
    # legacy rows + for senders who don't set a display name. Used by
    # the inbox presenter to surface "American Express" instead of the
    # VERP-style tracking mailbox.
    from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)  # plain text body (stripped)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)  # original HTML body (rendered in iframe)
    category: Mapped[str | None] = mapped_column(String(50))  # schedule, complaint, billing, gate_code, general, spam
    urgency: Mapped[str | None] = mapped_column(String(20))  # low, medium, high
    final_response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, sent, auto_sent, rejected, ignored
    approved_by: Mapped[str | None] = mapped_column(String(50))  # phone number or name
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matched_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    match_method: Mapped[str | None] = mapped_column(String(30))  # email, domain, company_name, sender_name, manual
    customer_name: Mapped[str | None] = mapped_column(String(200))
    property_address: Mapped[str | None] = mapped_column(String(300))
    delivered_to: Mapped[str | None] = mapped_column(String(255), nullable=True)  # org address that received the email
    # Per-message owner derived at ingest from Delivered-To → To → Cc → (outbound) From.
    # Populated by the historical ingest; live pipeline may backfill later. Email string,
    # not user_id — see is_historical note on AgentThread.
    received_by_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_threads.id"), index=True)
    postmark_message_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    rfc_message_id: Mapped[str | None] = mapped_column(String(500), index=True, nullable=True)  # RFC 5322 Message-ID header — cross-source dedup key
    delivery_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # delivered, bounced, opened, spam_complaint
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    thread = relationship("AgentThread", back_populates="messages")
