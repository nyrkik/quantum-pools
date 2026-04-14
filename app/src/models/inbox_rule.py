"""Inbox rules — unified sender/recipient pattern matching.

Replaces the older `inbox_routing_rules` + `suppressed_email_senders` pair.
See `docs/inbox-rules-unification-plan.md` for the migration rationale
and the scppool incident background.

Conditions are stored as JSONB array: [{field, operator, value}, ...]
All conditions must match (AND). Fields: sender_email | sender_domain |
recipient_email | subject | category | customer_id | body. Operators:
equals | contains | starts_with | ends_with | matches (glob).

Actions are stored as JSONB array: [{type, params}, ...]. Types:
assign_folder | assign_tag | assign_category | set_visibility |
suppress_contact_prompt | route_to_spam.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class InboxRule(Base):
    __tablename__ = "inbox_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index(
            "ix_inbox_rules_org_active_priority",
            "organization_id",
            "is_active",
            "priority",
        ),
    )
