"""add awaiting_reply_until to agent_threads

Promise tracker: when a customer says "I'll get back to you", the
orchestrator sets this column to NOW() + 7 days. A new inbound on the
thread clears it. Owner+admin dashboard widget queries this column to
surface threads where the customer went silent past their promise.

See `docs/promise-tracker-spec.md`.

Revision ID: 1c1891f70983
Revises: d237aedcbe98
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1c1891f70983"
down_revision: Union[str, None] = "d237aedcbe98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column("awaiting_reply_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_threads_awaiting_reply_until",
        "agent_threads",
        ["awaiting_reply_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_threads_awaiting_reply_until", table_name="agent_threads")
    op.drop_column("agent_threads", "awaiting_reply_until")
