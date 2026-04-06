"""Add token/cost tracking to deepblue_eval_runs

Revision ID: d5c2e1f97a84
Revises: c9f4d1e28b73
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5c2e1f97a84'
down_revision: str = 'c9f4d1e28b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deepblue_eval_runs', sa.Column('total_input_tokens', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('deepblue_eval_runs', sa.Column('total_output_tokens', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('deepblue_eval_runs', sa.Column('total_cost_usd', sa.Float(), nullable=False, server_default='0'))
    op.add_column('deepblue_eval_runs', sa.Column('duration_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('deepblue_eval_runs', 'duration_seconds')
    op.drop_column('deepblue_eval_runs', 'total_cost_usd')
    op.drop_column('deepblue_eval_runs', 'total_output_tokens')
    op.drop_column('deepblue_eval_runs', 'total_input_tokens')
