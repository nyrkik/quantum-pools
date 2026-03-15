"""drop is_primary from bodies_of_water

Revision ID: 2785866809e9
Revises: 8bc97367b50b
Create Date: 2026-03-14 17:36:04.728273

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2785866809e9'
down_revision: Union[str, None] = '8bc97367b50b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('bodies_of_water', 'is_primary')


def downgrade() -> None:
    op.add_column('bodies_of_water', sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'))
