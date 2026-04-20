"""OrgWorkflowConfig — per-org post-creation-handler configuration.

Phase 4 entity. One row per org (lazy-created on first write). Stores
the map of `entity_type → handler_name` that drives what happens after
a proposal creates something, plus the default-assignee strategy the
handlers that ask for an assignee consult.

System defaults live in `WorkflowConfigService.get_or_default` — orgs
without a row fall through to those defaults. See docs/ai-platform-phase-4.md §5.
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
