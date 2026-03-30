"""Add property_access_codes table

Revision ID: 63ecd9289c92
Revises: a1b2c3d4e5f6
Create Date: 2026-03-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '63ecd9289c92'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('property_access_codes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('property_id', sa.String(length=36), nullable=False),
        sa.Column('label', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_property_access_codes_property_id'), 'property_access_codes', ['property_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_property_access_codes_property_id'), table_name='property_access_codes')
    op.drop_table('property_access_codes')
