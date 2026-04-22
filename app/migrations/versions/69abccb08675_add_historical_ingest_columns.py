"""add historical ingest columns to agent_threads and agent_messages

Supports the historical Gmail ingest script
(app/scripts/import_historical_gmail.py) which imports pre-cutover
Sapphire mail as closed threads without triggering AI/events/notifications.

- agent_threads.is_historical: excludes from live inbox queries
- agent_threads.primary_owner_email: per-thread owner string (email, not
  user_id — stable across future mailbox reshuffles, email→user mapping
  lives in the user-inbox feature when built)
- agent_messages.received_by_email: per-message owner derived from
  Delivered-To / To / Cc / outbound From at ingest time

Partial index on (organization_id, is_historical) speeds "exclude
historical" inbox queries without touching the active-thread hot path.

Revision ID: 69abccb08675
Revises: e7a4c5f91d03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "69abccb08675"
down_revision: Union[str, None] = "e7a4c5f91d03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column(
            "is_historical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "agent_threads",
        sa.Column("primary_owner_email", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_messages",
        sa.Column("received_by_email", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_agent_threads_historical",
        "agent_threads",
        ["organization_id", "is_historical"],
        postgresql_where=sa.text("is_historical = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_threads_historical", table_name="agent_threads")
    op.drop_column("agent_messages", "received_by_email")
    op.drop_column("agent_threads", "primary_owner_email")
    op.drop_column("agent_threads", "is_historical")
