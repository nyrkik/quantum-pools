"""add body_html to agent_messages

Revision ID: e4a1b2c3d4e5
Revises: b1e2f3a4c5d6
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e4a1b2c3d4e5'
down_revision: Union[str, None] = 'b1e2f3a4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('agent_messages', sa.Column('body_html', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('agent_messages', 'body_html')
