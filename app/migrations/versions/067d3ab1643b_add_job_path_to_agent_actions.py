"""Add job_path to agent_actions

Revision ID: 067d3ab1643b
Revises: dbba13977814
Create Date: 2026-03-29 06:27:04.902490

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '067d3ab1643b'
down_revision: Union[str, None] = 'dbba13977814'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_actions', sa.Column('job_path', sa.String(length=20), server_default='internal', nullable=False))


def downgrade() -> None:
    op.drop_column('agent_actions', 'job_path')
