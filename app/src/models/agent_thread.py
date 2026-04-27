"""Agent conversation threads — groups related emails into conversations."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, text, false
from sqlalchemy.dialects.postgresql import JSONB
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
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, handled, archived (ignored is legacy — pre-2026-04-25 derivation set it for AI auto-closes; user-dismiss now derives to archived)
    urgency: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(50))
    message_count: Mapped[int] = mapped_column(Integer, default=1)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_direction: Mapped[str] = mapped_column(String(10), default="inbound")
    last_snippet: Mapped[str | None] = mapped_column(String(200))
    has_pending: Mapped[bool] = mapped_column(Boolean, default=True)
    has_open_actions: Mapped[bool] = mapped_column(Boolean, default=False)

    # Rule-driven "mark as read" stamp. When a mark_as_read rule fires we set
    # this to the message's received_at so the thread doesn't appear unread
    # for any user. If a later message arrives without the rule firing (rule
    # disabled/modified), last_message_at advances past auto_read_at and the
    # thread re-unreads naturally.
    auto_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Timestamp of the user's Yes/No acknowledgement on the auto-handled
    # feedback banner (AutoHandledFeedbackBanner in the thread detail).
    # Non-null means the user has reviewed the AI's auto-handle decision —
    # the banner no longer shows. Keeps the decision persisted across
    # sessions (the React `reviewed` state was local-only).
    auto_handled_feedback_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Set by the orchestrator when an inbound is auto-closed by the AI
    # without human input (no draft sent). Drives the AI Review folder
    # query (`auto_handled_at IS NOT NULL AND auto_handled_feedback_at IS NULL`)
    # and the row-level "AI" pill. Once set, never clears.
    auto_handled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    case_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_cases.id", ondelete="SET NULL"), index=True)

    # Gmail sync
    gmail_thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Gmail's thread ID for read/unread sync

    # Folder organization
    folder_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("inbox_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    folder_override: Mapped[bool] = mapped_column(Boolean, default=False)  # True = user manually moved, rules won't re-assign

    # Inbox routing / visibility — role-group list (built-in slugs like
    # "admin"/"manager" plus any custom role slugs). NULL means everyone
    # in the org sees the thread; otherwise the user's effective role
    # slug must appear in the list.
    visibility_role_slugs: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    delivered_to: Mapped[str | None] = mapped_column(String(255), nullable=True)  # org address that received the email

    # Thread assignment
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 3 — AI inbox summary cache. Populated by InboxSummarizerService
    # on inbound messages and a daily stale sweep. See
    # docs/ai-platform-phase-3.md §4 for payload shape.
    ai_summary_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_summary_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_summary_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False,
    )
    ai_summary_debounce_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Historical ingest — pre-cutover mail imported via app/scripts/import_historical_gmail.py.
    # `is_historical=True` threads are excluded from `/inbox` default queries and never queue
    # for AI/events/notifications. `primary_owner_email` is the derived per-thread owner (email
    # string, not user_id — stable across future mailbox reshuffles).
    is_historical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    primary_owner_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Promise tracker: when a customer says "I'll get back to you" the
    # orchestrator sets this to NOW() + 7 days. A subsequent inbound
    # clears it. Dashboard widget surfaces threads where this <= NOW().
    # See `docs/promise-tracker-spec.md`.
    awaiting_reply_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    case = relationship("ServiceCase", back_populates="threads", lazy="noload")
    messages = relationship("AgentMessage", back_populates="thread", order_by="AgentMessage.received_at")
