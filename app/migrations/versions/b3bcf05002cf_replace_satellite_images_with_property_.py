"""replace satellite_images with property_photos

Revision ID: b3bcf05002cf
Revises: 75f82d5141d5
Create Date: 2026-03-15 07:15:30.781157

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3bcf05002cf'
down_revision: Union[str, None] = '75f82d5141d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('satellite_images')

    op.create_table(
        'property_photos',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('property_id', sa.String(36), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('body_of_water_id', sa.String(36), sa.ForeignKey('bodies_of_water.id', ondelete='SET NULL'), nullable=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('caption', sa.String(200), nullable=True),
        sa.Column('is_hero', sa.Boolean, default=False, nullable=False),
        sa.Column('uploaded_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_property_photos_property_id', 'property_photos', ['property_id'])
    op.create_index('ix_property_photos_organization_id', 'property_photos', ['organization_id'])
    op.create_index('ix_property_photos_body_of_water_id', 'property_photos', ['body_of_water_id'])


def downgrade() -> None:
    op.drop_table('property_photos')

    op.create_table(
        'satellite_images',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('property_id', sa.String(36), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('center_lat', sa.Float, nullable=False),
        sa.Column('center_lng', sa.Float, nullable=False),
        sa.Column('zoom', sa.Integer, nullable=False),
        sa.Column('is_hero', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
