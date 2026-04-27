"""AgentProposal — staged AI outputs awaiting human resolution.

Phase 2 primitive. Every AI suggestion (drafted email, proposed job,
org_config recommendation, DeepBlue tool confirmation) becomes a row
here. `ProposalService` manages state transitions.

Schema reference: `docs/ai-platform-phase-2.md` §4.1.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    pass


# Valid status values — kept as module constants rather than an Enum
# so the values stay stable as strings across DB/API/tests.
STATUS_STAGED = "staged"
STATUS_ACCEPTED = "accepted"
STATUS_EDITED = "edited"            # accepted after human edits
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"          # age-based sweep
STATUS_SUPERSEDED = "superseded"    # replaced by a fresher proposal

ALL_STATUSES = (
    STATUS_STAGED, STATUS_ACCEPTED, STATUS_EDITED,
    STATUS_REJECTED, STATUS_EXPIRED, STATUS_SUPERSEDED,
)

# Terminal statuses — proposal is resolved, nothing more to do.
TERMINAL_STATUSES = (
    STATUS_ACCEPTED, STATUS_EDITED, STATUS_REJECTED,
    STATUS_EXPIRED, STATUS_SUPERSEDED,
)


class AgentProposal(Base):
    __tablename__ = "agent_proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Provenance. agent_type matches AgentLearningService constants.
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36))

    # The draft. Shape defined per-entity_type by the Pydantic schema
    # in `src/services/proposals/creators/<entity_type>.py`.
    proposed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    # Persistent natural-language summary the staging agent supplied
    # (e.g. "[default_assignee] 12 of 14 jobs went to Brian"). Forwarded
    # to AgentCorrection.input_context on resolve. Used by Phase 6
    # workflow_observer for per-detector threshold tuning, but
    # general-purpose for any agent that wants a breadcrumb that
    # survives the request cycle.
    input_context: Mapped[str | None] = mapped_column(Text)

    # State machine.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_STAGED,
    )
    rejected_permanently: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    superseded_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_proposals.id"),
    )

    # Outcome — polymorphic (entity_type, entity_id). Populated on
    # accept/edit. Not an FK because target table varies by entity_type.
    outcome_entity_type: Mapped[str | None] = mapped_column(String(50))
    outcome_entity_id: Mapped[str | None] = mapped_column(String(36))

    # RFC 6902 JSON patch describing the human's edits. Populated on
    # `edit_and_accept`. Learning signal consumes this to know what
    # specifically the user corrected.
    user_delta: Mapped[dict | None] = mapped_column(JSONB)

    # Resolution audit.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)

    # Lifecycle.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Self-referential — a superseding proposal points forward only; the
    # superseded proposal is found via superseded_by_id FK.
    superseded_by: Mapped["AgentProposal | None"] = relationship(
        "AgentProposal", remote_side=[id], lazy="noload",
    )
