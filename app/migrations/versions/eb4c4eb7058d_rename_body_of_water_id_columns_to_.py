"""rename body_of_water_id columns to water_feature_id

Revision ID: eb4c4eb7058d
Revises: cf0224edd42b
Create Date: 2026-03-22 16:38:14.355397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb4c4eb7058d'
down_revision: Union[str, None] = 'cf0224edd42b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "pool_measurements",
    "satellite_analyses",
    "chemical_readings",
    "chemical_cost_profiles",
    "dimension_estimates",
    "property_photos",
    "property_difficulties",
    "property_jurisdictions",
]


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, 'body_of_water_id', new_column_name='water_feature_id')


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, 'water_feature_id', new_column_name='body_of_water_id')
