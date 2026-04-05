"""Add case_id to deepblue_conversations

Revision ID: c3a8f5d21b94
Revises: b7d2e4f19a83
Create Date: 2026-04-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a8f5d21b94'
down_revision: str = 'b7d2e4f19a83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deepblue_conversations', sa.Column(
        'case_id', sa.String(36),
        sa.ForeignKey('service_cases.id', ondelete='SET NULL'),
        nullable=True, index=True,
    ))


def downgrade() -> None:
    op.drop_column('deepblue_conversations', 'case_id')
