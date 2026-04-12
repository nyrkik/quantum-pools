"""add rfc_message_id to agent_messages

Revision ID: a03da3580a92
Revises: aaf4a5dfc792
Create Date: 2026-04-12 06:44:59.543950

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a03da3580a92'
down_revision: Union[str, None] = 'aaf4a5dfc792'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_messages', sa.Column('rfc_message_id', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_agent_messages_rfc_message_id'), 'agent_messages', ['rfc_message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_messages_rfc_message_id'), table_name='agent_messages')
    op.drop_column('agent_messages', 'rfc_message_id')
