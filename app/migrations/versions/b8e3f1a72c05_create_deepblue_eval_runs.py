"""Create deepblue_eval_runs table

Revision ID: b8e3f1a72c05
Revises: a7f3c2e58d94
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8e3f1a72c05'
down_revision: str = 'a7f3c2e58d94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deepblue_eval_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('run_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('passed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('system_prompt_hash', sa.String(32), nullable=True),
        sa.Column('results_json', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table('deepblue_eval_runs')
