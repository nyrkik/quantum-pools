"""add auto_handled_at column + AI Review system folder

Splits the conflated `thread.status` field. `status="ignored"` was being
derived from "AI auto-closed an inbound without sending a reply" — but
the same string is also (rarely) set by explicit user dismissal. The
default Inbox query filters ignored, so legitimate auto-handled mail
(Workspace notifications, billing receipts) became invisible.

This migration:
- adds `agent_threads.auto_handled_at` (write-side timestamp; the
  existing `auto_handled_feedback_at` is the read-side ack)
- adds a partial index on the new column for the AI Review folder query
- seeds an `ai_review` system folder per org (sort_order 4 — between
  Spam and All Mail; existing All Mail and Historical bump to 5/6)

The orchestrator code change to write `auto_handled_at` ships in the
same backend deploy. A separate one-shot script
(`app/scripts/migrate_auto_handled_status.py`) backfills existing
status="ignored" rows that were really AI auto-closes.

Revision ID: d4f12b8e09a7
Revises: c33eb1accc84
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f12b8e09a7"
down_revision: Union[str, None] = "c33eb1accc84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column(
            "auto_handled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_agent_threads_auto_handled_at",
        "agent_threads",
        ["auto_handled_at"],
        postgresql_where=sa.text("auto_handled_at IS NOT NULL"),
    )

    op.execute("UPDATE inbox_folders SET sort_order = 5 WHERE system_key = 'all_mail'")
    op.execute("UPDATE inbox_folders SET sort_order = 6 WHERE system_key = 'historical'")

    op.execute(
        """
        INSERT INTO inbox_folders
          (id, organization_id, name, icon, sort_order, is_system, system_key, created_at, updated_at)
        SELECT
          gen_random_uuid()::text,
          o.id,
          'AI Review',
          'bot',
          4,
          true,
          'ai_review',
          now(),
          now()
        FROM organizations o
        WHERE NOT EXISTS (
          SELECT 1 FROM inbox_folders f
          WHERE f.organization_id = o.id AND f.system_key = 'ai_review'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_folders WHERE system_key = 'ai_review'")
    op.execute("UPDATE inbox_folders SET sort_order = 4 WHERE system_key = 'all_mail'")
    op.execute("UPDATE inbox_folders SET sort_order = 5 WHERE system_key = 'historical'")
    op.drop_index("ix_agent_threads_auto_handled_at", table_name="agent_threads")
    op.drop_column("agent_threads", "auto_handled_at")
