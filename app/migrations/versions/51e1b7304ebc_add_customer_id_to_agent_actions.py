"""Add customer_id to agent_actions

Revision ID: 51e1b7304ebc
Revises: 3c280dbb7fc2
Create Date: 2026-03-28 05:26:54.975656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '51e1b7304ebc'
down_revision: Union[str, None] = '3c280dbb7fc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_actions', sa.Column('customer_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_agent_actions_customer_id'), 'agent_actions', ['customer_id'], unique=False)
    op.create_foreign_key('fk_agent_actions_customer_id', 'agent_actions', 'customers', ['customer_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_agent_actions_customer_id', 'agent_actions', type_='foreignkey')
    op.drop_index(op.f('ix_agent_actions_customer_id'), table_name='agent_actions')
    op.drop_column('agent_actions', 'customer_id')
