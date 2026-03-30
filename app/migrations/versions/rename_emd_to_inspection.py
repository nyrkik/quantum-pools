"""Rename emd tables to inspection

Revision ID: a1b2c3d4e5f6
Revises: 4ce80b53793b
Create Date: 2026-03-30

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '4ce80b53793b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('emd_facilities', 'inspection_facilities')
    op.rename_table('emd_inspections', 'inspections')
    op.rename_table('emd_violations', 'inspection_violations')
    op.rename_table('emd_equipment', 'inspection_equipment')
    op.rename_table('emd_lookups', 'inspection_lookups')


def downgrade() -> None:
    op.rename_table('inspection_facilities', 'emd_facilities')
    op.rename_table('inspections', 'emd_inspections')
    op.rename_table('inspection_violations', 'emd_violations')
    op.rename_table('inspection_equipment', 'emd_equipment')
    op.rename_table('inspection_lookups', 'emd_lookups')
