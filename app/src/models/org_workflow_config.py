"""OrgWorkflowConfig — per-org post-creation-handler configuration.

One row per org (lazy-created on first write). Stores the map of
`entity_type → handler_name` that drives what happens after a proposal
creates something, plus the default-assignee strategy that the handlers
asking for an assignee consult.

Phase 6 adds `observer_mutes` and `observer_thresholds` for the
`workflow_observer` agent — the mute list + per-detector self-tuned
confidence thresholds.

System defaults live in `WorkflowConfigService.get_or_default` — orgs
without a row fall through to those defaults.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class OrgWorkflowConfig(Base):
    __tablename__ = "org_workflow_config"

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # e.g. {"job": "assign_inline"} — absent keys fall through to
    # system defaults so missing rows behave as pre-Phase-4.
    post_creation_handlers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    # e.g. {"strategy": "last_used_in_org", "fallback_user_id": null}
    default_assignee_strategy: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {"strategy": "last_used_in_org"},
    )
    # Phase 6. {"<detector_id>": {"muted_at": "<iso>", "muted_by_user_id": "<uuid>"}}
    # Presence of a key = workflow_observer skips that detector for this org.
    observer_mutes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    # Phase 6. {"<detector_id>": <float>} — per-detector self-tuned thresholds.
    # Absent key = use detector's default. Symmetric snap-back per scan.
    observer_thresholds: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
