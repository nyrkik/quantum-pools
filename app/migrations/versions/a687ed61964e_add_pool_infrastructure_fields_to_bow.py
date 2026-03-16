"""add pool infrastructure fields to bow

Revision ID: a687ed61964e
Revises: 400445d43eb7
Create Date: 2026-03-16 04:17:35.348670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a687ed61964e'
down_revision: Union[str, None] = '400445d43eb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bodies_of_water', sa.Column('fill_method', sa.String(50), nullable=True))
    op.add_column('bodies_of_water', sa.Column('drain_type', sa.String(50), nullable=True))
    op.add_column('bodies_of_water', sa.Column('drain_method', sa.String(50), nullable=True))
    op.add_column('bodies_of_water', sa.Column('drain_count', sa.Integer(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('drain_cover_compliant', sa.Boolean(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('drain_cover_install_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bodies_of_water', sa.Column('drain_cover_expiry_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bodies_of_water', sa.Column('equalizer_cover_compliant', sa.Boolean(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('equalizer_cover_install_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bodies_of_water', sa.Column('equalizer_cover_expiry_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bodies_of_water', sa.Column('plumbing_size_inches', sa.Float(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('pool_cover_type', sa.String(50), nullable=True))
    op.add_column('bodies_of_water', sa.Column('turnover_hours', sa.Float(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('skimmer_count', sa.Integer(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('equipment_year', sa.Integer(), nullable=True))
    op.add_column('bodies_of_water', sa.Column('equipment_pad_location', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('bodies_of_water', 'equipment_pad_location')
    op.drop_column('bodies_of_water', 'equipment_year')
    op.drop_column('bodies_of_water', 'skimmer_count')
    op.drop_column('bodies_of_water', 'turnover_hours')
    op.drop_column('bodies_of_water', 'pool_cover_type')
    op.drop_column('bodies_of_water', 'plumbing_size_inches')
    op.drop_column('bodies_of_water', 'equalizer_cover_expiry_date')
    op.drop_column('bodies_of_water', 'equalizer_cover_install_date')
    op.drop_column('bodies_of_water', 'equalizer_cover_compliant')
    op.drop_column('bodies_of_water', 'drain_cover_expiry_date')
    op.drop_column('bodies_of_water', 'drain_cover_install_date')
    op.drop_column('bodies_of_water', 'drain_cover_compliant')
    op.drop_column('bodies_of_water', 'drain_count')
    op.drop_column('bodies_of_water', 'drain_method')
    op.drop_column('bodies_of_water', 'drain_type')
    op.drop_column('bodies_of_water', 'fill_method')
