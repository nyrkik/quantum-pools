"""add_efficiency_multiplier_to_techs

Revision ID: 4019b4ba8ca1
Revises: 557edb116acf
Create Date: 2025-11-01 05:41:23.212843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4019b4ba8ca1'
down_revision: Union[str, None] = '557edb116acf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add efficiency_multiplier column to techs table
    op.add_column('techs', sa.Column('efficiency_multiplier', sa.Float(), nullable=False, server_default='1.0'))


def downgrade() -> None:
    # Remove efficiency_multiplier column from techs table
    op.drop_column('techs', 'efficiency_multiplier')
