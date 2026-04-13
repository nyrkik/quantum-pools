"""add delivery status tracking to agent_messages

Revision ID: f5b2c3d4e5f6
Revises: e4a1b2c3d4e5
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f5b2c3d4e5f6'
down_revision: Union[str, None] = 'e4a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('agent_messages', sa.Column('delivery_status', sa.String(length=20), nullable=True))
    op.add_column('agent_messages', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_messages', sa.Column('first_opened_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_messages', sa.Column('open_count', sa.Integer(), nullable=False, server_default='0'))

def downgrade() -> None:
    op.drop_column('agent_messages', 'open_count')
    op.drop_column('agent_messages', 'first_opened_at')
    op.drop_column('agent_messages', 'delivered_at')
    op.drop_column('agent_messages', 'delivery_status')
