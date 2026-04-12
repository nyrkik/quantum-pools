"""add suppressed_email_senders table

Revision ID: c83747803796
Revises: a03da3580a92
Create Date: 2026-04-12 06:50:19.461472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c83747803796'
down_revision: Union[str, None] = 'a03da3580a92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('suppressed_email_senders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('email_pattern', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=50), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_suppressed_email_senders_organization_id', 'suppressed_email_senders', ['organization_id'])


def downgrade() -> None:
    op.drop_index('ix_suppressed_email_senders_organization_id', table_name='suppressed_email_senders')
    op.drop_table('suppressed_email_senders')
