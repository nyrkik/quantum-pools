"""add auto_read_at to agent_threads for mark_as_read rules

Revision ID: 5442e2305513
Revises: f8f870f74d15
Create Date: 2026-04-14 04:31:06.061114

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5442e2305513'
down_revision: Union[str, None] = 'f8f870f74d15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_threads',
        sa.Column('auto_read_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('agent_threads', 'auto_read_at')
