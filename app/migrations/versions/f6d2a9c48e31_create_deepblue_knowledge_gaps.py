"""Create deepblue_knowledge_gaps table

Revision ID: f6d2a9c48e31
Revises: e5c1d8f43a27
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6d2a9c48e31'
down_revision: str = 'e5c1d8f43a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deepblue_knowledge_gaps',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('conversation_id', sa.String(36), nullable=True, index=True),
        sa.Column('user_question', sa.Text(), nullable=False),
        sa.Column('resolution', sa.String(20), nullable=False),
        sa.Column('sql_query', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('result_row_count', sa.Integer(), nullable=True),
        sa.Column('reviewed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('promoted_to_tool', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table('deepblue_knowledge_gaps')
