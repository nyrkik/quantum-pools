"""InboxFolder — org-level organizational buckets for agent threads.

System folders (Inbox, Sent, Automated, Spam) are seeded per org and
cannot be deleted or renamed. Custom folders can be created by users.

Threads reference folders via `agent_threads.folder_id` FK. NULL = Inbox.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class InboxFolder(Base):
    __tablename__ = "inbox_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50))  # lucide icon name
    color: Mapped[str | None] = mapped_column(String(20))  # tailwind color token
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    system_key: Mapped[str | None] = mapped_column(String(20))  # inbox, sent, automated, spam
    gmail_label_id: Mapped[str | None] = mapped_column(String(200))  # Phase 3: Gmail label sync

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "system_key", name="uq_inbox_folders_org_system_key"),
    )


SYSTEM_FOLDERS = [
    {"system_key": "inbox", "name": "Inbox", "icon": "inbox", "sort_order": 0},
    # Outbox = outbound messages that haven't completed (queued, failed,
    # bounced, or delivery_error). Replaces the "Failed" filter chip —
    # Gmail-like mental model ("where did my email go? check Outbox").
    # Language is "not sent yet", not "failed", so users aren't alarmed by
    # transient queue states. Badge shows count only when > 0.
    {"system_key": "outbox", "name": "Outbox", "icon": "clock", "sort_order": 1},
    {"system_key": "sent", "name": "Sent", "icon": "send", "sort_order": 2},
    {"system_key": "spam", "name": "Spam", "icon": "shield-alert", "sort_order": 3},
    # AI Review = threads the AI auto-closed without sending a reply
    # (`auto_handled_at IS NOT NULL AND auto_handled_feedback_at IS NULL`).
    # Owner+admin only — surfaces the classifier's silent decisions so the
    # user can spot mis-handles (e.g. legitimate Workspace notifications
    # classified as no_response). Amber badge to distinguish from Outbox red.
    {"system_key": "ai_review", "name": "AI Review", "icon": "bot", "sort_order": 4},
    # All Mail = escape hatch showing EVERY live (non-historical) thread
    # regardless of status, folder, or direction. The "where's my email?"
    # failsafe — if QP's AI auto-handled a message into a folder, this is
    # where users find it. Distinct from Historical, which only shows
    # pre-cutover imports. Gated by inbox.see_all_mail.
    {"system_key": "all_mail", "name": "All Mail", "icon": "mailbox", "sort_order": 5},
    # Historical = pre-cutover mail imported via app/scripts/import_historical_gmail.py
    # (see agent_threads.is_historical). Exclusive view of historical threads only —
    # sent/spam/active live in their own folders.
    {"system_key": "historical", "name": "Historical", "icon": "archive", "sort_order": 6},
]
