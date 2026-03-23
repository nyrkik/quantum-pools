"""add wf-level difficulty scores to bodies_of_water

Revision ID: 339eab0db3fe
Revises: 91ba6105c49f
Create Date: 2026-03-22 09:05:51.340983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '339eab0db3fe'
down_revision: Union[str, None] = '91ba6105c49f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bodies_of_water', sa.Column('access_difficulty', sa.Float(), nullable=False, server_default='1.0'))
    op.add_column('bodies_of_water', sa.Column('chemical_demand', sa.Float(), nullable=False, server_default='1.0'))
    op.add_column('bodies_of_water', sa.Column('equipment_effectiveness', sa.Float(), nullable=False, server_default='3.0'))
    op.add_column('bodies_of_water', sa.Column('pool_design', sa.Float(), nullable=False, server_default='3.0'))

    # Backfill from property_difficulties where they exist
    op.execute("""
        UPDATE bodies_of_water b
        SET access_difficulty = pd.access_difficulty_score,
            chemical_demand = pd.chemical_demand_score,
            equipment_effectiveness = pd.equipment_effectiveness,
            pool_design = pd.pool_design_score
        FROM property_difficulties pd
        WHERE pd.property_id = b.property_id
    """)


def downgrade() -> None:
    op.drop_column('bodies_of_water', 'pool_design')
    op.drop_column('bodies_of_water', 'equipment_effectiveness')
    op.drop_column('bodies_of_water', 'chemical_demand')
    op.drop_column('bodies_of_water', 'access_difficulty')
