"""add pool_lat pool_lng to satellite_analyses

Revision ID: 3013e93226ce
Revises: f25ace767c55
Create Date: 2026-03-14 15:52:55.945860

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3013e93226ce'
down_revision: Union[str, None] = 'f25ace767c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('satellite_analyses', sa.Column('pool_lat', sa.Float(), nullable=True))
    op.add_column('satellite_analyses', sa.Column('pool_lng', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('satellite_analyses', 'pool_lng')
    op.drop_column('satellite_analyses', 'pool_lat')
