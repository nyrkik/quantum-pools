"""rename bodies_of_water table to water_features

Revision ID: cf0224edd42b
Revises: 8a3b2d7b8d3b
Create Date: 2026-03-22 09:25:15.159440

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf0224edd42b'
down_revision: Union[str, None] = '8a3b2d7b8d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('bodies_of_water', 'water_features')
    # Update FK references in other tables
    op.execute("ALTER TABLE pool_measurements DROP CONSTRAINT IF EXISTS pool_measurements_body_of_water_id_fkey")
    op.execute("ALTER TABLE pool_measurements ADD CONSTRAINT pool_measurements_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE chemical_readings DROP CONSTRAINT IF EXISTS chemical_readings_body_of_water_id_fkey")
    op.execute("ALTER TABLE chemical_readings ADD CONSTRAINT chemical_readings_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE satellite_analyses DROP CONSTRAINT IF EXISTS satellite_analyses_body_of_water_id_fkey")
    op.execute("ALTER TABLE satellite_analyses ADD CONSTRAINT satellite_analyses_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE property_difficulties DROP CONSTRAINT IF EXISTS property_difficulties_body_of_water_id_fkey")
    op.execute("ALTER TABLE property_difficulties ADD CONSTRAINT property_difficulties_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE property_jurisdictions DROP CONSTRAINT IF EXISTS property_jurisdictions_body_of_water_id_fkey")
    op.execute("ALTER TABLE property_jurisdictions ADD CONSTRAINT property_jurisdictions_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE dimension_estimates DROP CONSTRAINT IF EXISTS dimension_estimates_body_of_water_id_fkey")
    op.execute("ALTER TABLE dimension_estimates ADD CONSTRAINT dimension_estimates_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE chemical_cost_profiles DROP CONSTRAINT IF EXISTS chemical_cost_profiles_body_of_water_id_fkey")
    op.execute("ALTER TABLE chemical_cost_profiles ADD CONSTRAINT chemical_cost_profiles_body_of_water_id_fkey FOREIGN KEY (body_of_water_id) REFERENCES water_features(id) ON DELETE CASCADE")


def downgrade() -> None:
    op.rename_table('water_features', 'bodies_of_water')
