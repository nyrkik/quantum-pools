"""add gmail_thread_id to agent_threads

Revision ID: b1e2f3a4c5d6
Revises: 544070485a96
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b1e2f3a4c5d6'
down_revision: Union[str, None] = '544070485a96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('agent_threads', sa.Column('gmail_thread_id', sa.String(length=100), nullable=True))

def downgrade() -> None:
    op.drop_column('agent_threads', 'gmail_thread_id')
