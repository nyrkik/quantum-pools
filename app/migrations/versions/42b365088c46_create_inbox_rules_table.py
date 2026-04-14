"""create inbox_rules table

Unified replacement for inbox_routing_rules + suppressed_email_senders.
See docs/inbox-rules-unification-plan.md.

Revision ID: 42b365088c46
Revises: 2d1e5fa92f88
Create Date: 2026-04-14 03:52:43.168766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '42b365088c46'
down_revision: Union[str, None] = '2d1e5fa92f88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inbox_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('conditions', postgresql.JSONB(), nullable=False),
        sa.Column('actions', postgresql.JSONB(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.create_index(
        'ix_inbox_rules_org_active_priority',
        'inbox_rules',
        ['organization_id', 'is_active', 'priority'],
    )


def downgrade() -> None:
    op.drop_index('ix_inbox_rules_org_active_priority', table_name='inbox_rules')
    op.drop_table('inbox_rules')
