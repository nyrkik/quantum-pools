"""add customer_contacts table

Revision ID: e2e2f726e450
Revises: 63ecd9289c92
Create Date: 2026-03-30 16:43:03.133723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2e2f726e450'
down_revision: Union[str, None] = '63ecd9289c92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('customer_contacts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('customer_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('receives_estimates', sa.Boolean(), nullable=False),
    sa.Column('receives_invoices', sa.Boolean(), nullable=False),
    sa.Column('receives_service_updates', sa.Boolean(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_contacts_customer_id'), 'customer_contacts', ['customer_id'], unique=False)
    op.create_index(op.f('ix_customer_contacts_organization_id'), 'customer_contacts', ['organization_id'], unique=False)

    # Clean up leftover emd_ prefixed indexes from the EMD→Inspection rename
    for old, new, table in [
        ('ix_emd_equipment_facility_id', 'ix_inspection_equipment_facility_id', 'inspection_equipment'),
        ('ix_emd_equipment_inspection_id', 'ix_inspection_equipment_inspection_id', 'inspection_equipment'),
        ('ix_emd_facilities_facility_id', 'ix_inspection_facilities_facility_id', 'inspection_facilities'),
        ('ix_emd_facilities_matched_property_id', 'ix_inspection_facilities_matched_property_id', 'inspection_facilities'),
        ('ix_emd_facilities_organization_id', 'ix_inspection_facilities_organization_id', 'inspection_facilities'),
        ('ix_emd_lookups_facility_id', 'ix_inspection_lookups_facility_id', 'inspection_lookups'),
        ('ix_emd_lookups_organization_id', 'ix_inspection_lookups_organization_id', 'inspection_lookups'),
        ('ix_emd_violations_facility_id', 'ix_inspection_violations_facility_id', 'inspection_violations'),
        ('ix_emd_violations_inspection_id', 'ix_inspection_violations_inspection_id', 'inspection_violations'),
        ('ix_emd_inspections_facility_id', 'ix_inspections_facility_id', 'inspections'),
        ('ix_emd_inspections_inspection_date', 'ix_inspections_inspection_date', 'inspections'),
        ('ix_emd_inspections_inspection_id', 'ix_inspections_inspection_id', 'inspections'),
        ('ix_emd_inspections_permit_id', 'ix_inspections_permit_id', 'inspections'),
    ]:
        op.execute(f'ALTER INDEX IF EXISTS {old} RENAME TO {new}')

    # Drop orphaned thread_reads table (replaced by notification system)
    op.drop_table('thread_reads')


def downgrade() -> None:
    op.drop_index(op.f('ix_customer_contacts_organization_id'), table_name='customer_contacts')
    op.drop_index(op.f('ix_customer_contacts_customer_id'), table_name='customer_contacts')
    op.drop_table('customer_contacts')
