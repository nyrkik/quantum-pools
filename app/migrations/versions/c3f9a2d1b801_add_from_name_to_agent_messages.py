"""add from_name to agent_messages

Sender display name captured at ingest from the raw From header
(e.g. "American Express" from ``American Express <r_xxx@…>``). Lets
the inbox row show a human name for senders that use VERP-style
per-email tracking addresses (AmEx, Poolcorp bounces, marketing
platforms). Legacy rows stay NULL — the original From header is not
stored anywhere retrievable, so population is forward-only.

See docs/email-body-pipeline-refactor.md §2.3.

Revision ID: c3f9a2d1b801
Revises: b7e4a21c9f10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f9a2d1b801"
down_revision: Union[str, None] = "b7e4a21c9f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_messages",
        sa.Column("from_name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_messages", "from_name")
