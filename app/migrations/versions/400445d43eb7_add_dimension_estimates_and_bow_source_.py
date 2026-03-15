"""add_dimension_estimates_and_bow_source_tracking

Revision ID: 400445d43eb7
Revises: b3bcf05002cf
Create Date: 2026-03-15 08:54:20.414725

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '400445d43eb7'
down_revision: Union[str, None] = 'b3bcf05002cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create dimension_estimates table
    op.create_table('dimension_estimates',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('body_of_water_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('estimated_sqft', sa.Float(), nullable=True),
    sa.Column('perimeter_ft', sa.Float(), nullable=True),
    sa.Column('raw_data', sa.JSON(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['body_of_water_id'], ['bodies_of_water.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dimension_estimates_body_of_water_id'), 'dimension_estimates', ['body_of_water_id'], unique=False)
    op.create_index(op.f('ix_dimension_estimates_organization_id'), 'dimension_estimates', ['organization_id'], unique=False)

    # Add dimension tracking columns to bodies_of_water
    op.add_column('bodies_of_water', sa.Column('dimension_source', sa.String(length=20), nullable=True))
    op.add_column('bodies_of_water', sa.Column('dimension_source_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bodies_of_water', sa.Column('perimeter_ft', sa.Float(), nullable=True))

    # Backfill dimension_source for existing BOWs that have pool_sqft
    conn = op.get_bind()

    # BOWs with measurement-applied sqft (pool_measurements with applied_to_property=true and matching body_of_water_id)
    conn.execute(sa.text("""
        UPDATE bodies_of_water bow
        SET dimension_source = 'measurement',
            dimension_source_date = pm.created_at
        FROM pool_measurements pm
        WHERE pm.body_of_water_id = bow.id
          AND pm.applied_to_property = true
          AND bow.pool_sqft IS NOT NULL
          AND bow.dimension_source IS NULL
    """))

    # BOWs with satellite analysis that has estimated_pool_sqft
    conn.execute(sa.text("""
        UPDATE bodies_of_water bow
        SET dimension_source = 'satellite',
            dimension_source_date = sa2.created_at
        FROM satellite_analyses sa2
        WHERE sa2.body_of_water_id = bow.id
          AND sa2.estimated_pool_sqft IS NOT NULL
          AND sa2.pool_detected = true
          AND bow.pool_sqft IS NOT NULL
          AND bow.dimension_source IS NULL
    """))

    # Remaining BOWs with pool_sqft but no source yet => manual
    conn.execute(sa.text("""
        UPDATE bodies_of_water
        SET dimension_source = 'manual'
        WHERE pool_sqft IS NOT NULL
          AND dimension_source IS NULL
    """))


def downgrade() -> None:
    op.drop_column('bodies_of_water', 'perimeter_ft')
    op.drop_column('bodies_of_water', 'dimension_source_date')
    op.drop_column('bodies_of_water', 'dimension_source')
    op.drop_index(op.f('ix_dimension_estimates_organization_id'), table_name='dimension_estimates')
    op.drop_index(op.f('ix_dimension_estimates_body_of_water_id'), table_name='dimension_estimates')
    op.drop_table('dimension_estimates')
