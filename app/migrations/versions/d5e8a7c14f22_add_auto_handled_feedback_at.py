"""add auto_handled_feedback_at to agent_threads

When the AI auto-handles a thread (hides from inbox without sending),
the thread-detail view shows a "AI moved this to X. Was that right?"
banner. Until this column existed the banner's "dismissed" state was
only local to the React component, so reopening the thread brought
the banner back — clicking Yes twice had no persistent effect.

This column stores the timestamp of the user's acknowledgement (Yes
OR No). Presenter reads it into the derived ``is_auto_handled`` flag
so a dismissed banner stays dismissed across sessions.

Revision ID: d5e8a7c14f22
Revises: c3f9a2d1b801
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e8a7c14f22"
down_revision: Union[str, None] = "c3f9a2d1b801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column(
            "auto_handled_feedback_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_threads", "auto_handled_feedback_at")
