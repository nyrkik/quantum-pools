"""phase3 inbox summarizer columns + flag

Phase 3 Step 1 migration. See docs/ai-platform-phase-3.md §3-§5.

Adds:
- agent_threads.ai_summary_payload jsonb — cached AI summary.
- agent_threads.ai_summary_generated_at tstz — cache age for the
  stale-sweep (regenerate >7 days old).
- agent_threads.ai_summary_version int — bump when schema changes;
  old versions are implicitly stale.
- agent_threads.ai_summary_debounce_until tstz — set when an inbound
  arrives; the APScheduler sweep regenerates once this passes.
- organizations.inbox_v2_enabled bool — per-org UX rollout flag for
  the inbox redesign (default false; platform-admin toggles).

Revision ID: 45c1d6086806
Revises: c5cb98f55580
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision: str = '45c1d6086806'
down_revision: Union[str, None] = 'c5cb98f55580'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column("ai_summary_payload", pg.JSONB(), nullable=True),
    )
    op.add_column(
        "agent_threads",
        sa.Column("ai_summary_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_threads",
        sa.Column(
            "ai_summary_version", sa.Integer(),
            nullable=False, server_default="0",  # 0 = never generated
        ),
    )
    op.add_column(
        "agent_threads",
        sa.Column("ai_summary_debounce_until", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index — debounce sweep reads only rows waiting to fire.
    op.create_index(
        "ix_agent_threads_summary_due",
        "agent_threads",
        ["ai_summary_debounce_until"],
        postgresql_where=sa.text("ai_summary_debounce_until IS NOT NULL"),
    )

    op.add_column(
        "organizations",
        sa.Column(
            "inbox_v2_enabled", sa.Boolean(),
            nullable=False, server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "inbox_v2_enabled")
    op.drop_index("ix_agent_threads_summary_due", table_name="agent_threads")
    op.drop_column("agent_threads", "ai_summary_debounce_until")
    op.drop_column("agent_threads", "ai_summary_version")
    op.drop_column("agent_threads", "ai_summary_generated_at")
    op.drop_column("agent_threads", "ai_summary_payload")
