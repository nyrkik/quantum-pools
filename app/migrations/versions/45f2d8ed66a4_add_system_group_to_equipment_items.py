"""Add system_group to equipment_items

Revision ID: 45f2d8ed66a4
Revises: 51e1b7304ebc
Create Date: 2026-03-28 08:47:36.073598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '45f2d8ed66a4'
down_revision: Union[str, None] = '51e1b7304ebc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('equipment_items', sa.Column('system_group', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('equipment_items', 'system_group')
