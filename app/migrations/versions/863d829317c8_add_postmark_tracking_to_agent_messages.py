"""add postmark tracking to agent_messages

Revision ID: 863d829317c8
Revises: 23323b58b603
Create Date: 2026-04-09 17:11:30.402565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '863d829317c8'
down_revision: Union[str, None] = '23323b58b603'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_messages', sa.Column('postmark_message_id', sa.String(length=100), nullable=True))
    op.add_column('agent_messages', sa.Column('delivery_error', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_agent_messages_postmark_message_id'), 'agent_messages', ['postmark_message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_messages_postmark_message_id'), table_name='agent_messages')
    op.drop_column('agent_messages', 'delivery_error')
    op.drop_column('agent_messages', 'postmark_message_id')
