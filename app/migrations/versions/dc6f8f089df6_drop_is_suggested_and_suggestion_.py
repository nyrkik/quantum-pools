"""drop is_suggested and suggestion_confidence from agent_actions

Revision ID: dc6f8f089df6
Revises: 74f28675fe9b
Create Date: 2026-04-14 19:39:05.364654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc6f8f089df6'
down_revision: Union[str, None] = '74f28675fe9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("agent_actions", "is_suggested")
    op.drop_column("agent_actions", "suggestion_confidence")


def downgrade() -> None:
    op.add_column(
        "agent_actions",
        sa.Column("suggestion_confidence", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "agent_actions",
        sa.Column("is_suggested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
