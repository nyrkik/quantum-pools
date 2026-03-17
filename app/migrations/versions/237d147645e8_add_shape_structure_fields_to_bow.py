"""add shape structure fields to bow

Revision ID: 237d147645e8
Revises: 2f849d9d94e2
Create Date: 2026-03-17 05:28:49.348834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '237d147645e8'
down_revision: Union[str, None] = '2f849d9d94e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bodies_of_water', sa.Column('has_rounded_corners', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('bodies_of_water', sa.Column('step_entry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('bodies_of_water', sa.Column('has_bench_shelf', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('bodies_of_water', 'has_bench_shelf')
    op.drop_column('bodies_of_water', 'step_entry_count')
    op.drop_column('bodies_of_water', 'has_rounded_corners')
