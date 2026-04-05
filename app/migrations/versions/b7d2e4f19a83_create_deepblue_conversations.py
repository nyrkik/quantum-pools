"""Create deepblue_conversations table

Revision ID: b7d2e4f19a83
Revises: a1f3c8d92e47
Create Date: 2026-04-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d2e4f19a83'
down_revision: str = 'a1f3c8d92e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deepblue_conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('context_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('messages_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('model_tier', sa.String(20), nullable=False, server_default='fast'),
        sa.Column('total_input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('deepblue_conversations')
