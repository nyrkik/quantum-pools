"""Rename drivers to techs throughout database

Revision ID: 557edb116acf
Revises: 9049f39ec8c1
Create Date: 2025-10-26 12:36:11.011391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '557edb116acf'
down_revision: Union[str, None] = '9049f39ec8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Drop foreign key constraints that reference drivers table
    op.drop_constraint('routes_driver_id_fkey', 'routes', type_='foreignkey')
    op.drop_constraint('customers_assigned_driver_id_fkey', 'customers', type_='foreignkey')

    # Step 2: Rename columns in related tables
    op.alter_column('routes', 'driver_id', new_column_name='tech_id')
    op.alter_column('customers', 'assigned_driver_id', new_column_name='assigned_tech_id')

    # Step 3: Rename the drivers table to techs
    op.rename_table('drivers', 'techs')

    # Step 4: Rename indexes on techs table
    op.execute('ALTER INDEX drivers_pkey RENAME TO techs_pkey')
    op.execute('ALTER INDEX idx_drivers_geocoding_provider RENAME TO idx_techs_geocoding_provider')
    op.execute('ALTER INDEX idx_drivers_org RENAME TO idx_techs_org')
    op.execute('ALTER INDEX ix_drivers_id RENAME TO ix_techs_id')
    op.execute('ALTER INDEX ix_drivers_name RENAME TO ix_techs_name')

    # Step 5: Rename indexes on routes table
    op.execute('ALTER INDEX ix_routes_driver_id RENAME TO ix_routes_tech_id')

    # Step 6: Rename foreign key constraint on techs table
    op.drop_constraint('fk_drivers_organization', 'techs', type_='foreignkey')
    op.create_foreign_key('fk_techs_organization', 'techs', 'organizations', ['organization_id'], ['id'])

    # Step 7: Recreate foreign key constraints with new names
    op.create_foreign_key('routes_tech_id_fkey', 'routes', 'techs', ['tech_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('customers_assigned_tech_id_fkey', 'customers', 'techs', ['assigned_tech_id'], ['id'])


def downgrade() -> None:
    # Reverse all operations
    # Step 1: Drop new foreign key constraints
    op.drop_constraint('routes_tech_id_fkey', 'routes', type_='foreignkey')
    op.drop_constraint('customers_assigned_tech_id_fkey', 'customers', type_='foreignkey')

    # Step 2: Rename foreign key constraint back
    op.drop_constraint('fk_techs_organization', 'techs', type_='foreignkey')
    op.create_foreign_key('fk_drivers_organization', 'techs', 'organizations', ['organization_id'], ['id'])

    # Step 3: Rename indexes back
    op.execute('ALTER INDEX ix_routes_tech_id RENAME TO ix_routes_driver_id')
    op.execute('ALTER INDEX ix_techs_name RENAME TO ix_drivers_name')
    op.execute('ALTER INDEX ix_techs_id RENAME TO ix_drivers_id')
    op.execute('ALTER INDEX idx_techs_org RENAME TO idx_drivers_org')
    op.execute('ALTER INDEX idx_techs_geocoding_provider RENAME TO idx_drivers_geocoding_provider')
    op.execute('ALTER INDEX techs_pkey RENAME TO drivers_pkey')

    # Step 4: Rename the techs table back to drivers
    op.rename_table('techs', 'drivers')

    # Step 5: Rename columns back in related tables
    op.alter_column('customers', 'assigned_tech_id', new_column_name='assigned_driver_id')
    op.alter_column('routes', 'tech_id', new_column_name='driver_id')

    # Step 6: Recreate original foreign key constraints
    op.create_foreign_key('customers_assigned_driver_id_fkey', 'customers', 'drivers', ['assigned_driver_id'], ['id'])
    op.create_foreign_key('routes_driver_id_fkey', 'routes', 'drivers', ['driver_id'], ['id'], ondelete='CASCADE')
