"""Add is_suggested and suggestion_confidence to agent_actions

Revision ID: 3c280dbb7fc2
Revises: b855dcc521a7
Create Date: 2026-03-27 16:15:07.787283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3c280dbb7fc2'
down_revision: Union[str, None] = 'b855dcc521a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_actions', sa.Column('is_suggested', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('agent_actions', sa.Column('suggestion_confidence', sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_actions', 'suggestion_confidence')
    op.drop_column('agent_actions', 'is_suggested')
