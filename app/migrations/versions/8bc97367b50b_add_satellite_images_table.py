"""add satellite_images table

Revision ID: 8bc97367b50b
Revises: 3013e93226ce
Create Date: 2026-03-14 16:52:47.935080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bc97367b50b'
down_revision: Union[str, None] = '3013e93226ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'satellite_images',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('property_id', sa.String(36), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('center_lat', sa.Float(), nullable=False),
        sa.Column('center_lng', sa.Float(), nullable=False),
        sa.Column('zoom', sa.Integer(), nullable=False),
        sa.Column('is_hero', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('satellite_images')
