"""Create broadcast_emails table

Revision ID: d4b9c7e32f15
Revises: c3a8f5d21b94
Create Date: 2026-04-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4b9c7e32f15'
down_revision: str = 'c3a8f5d21b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'broadcast_emails',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('filter_type', sa.String(50), nullable=False, server_default='all_active'),
        sa.Column('filter_data', sa.Text(), nullable=True),
        sa.Column('recipient_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('broadcast_emails')
