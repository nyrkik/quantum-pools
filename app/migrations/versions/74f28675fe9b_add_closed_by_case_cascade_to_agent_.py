"""add closed_by_case_cascade to agent_actions

Revision ID: 74f28675fe9b
Revises: 6ca65f3faef6
Create Date: 2026-04-14 18:49:34.073157

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74f28675fe9b'
down_revision: Union[str, None] = '6ca65f3faef6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_actions",
        sa.Column(
            "closed_by_case_cascade",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_actions", "closed_by_case_cascade")
