"""add permit_url column to inspections

Revision ID: e8deb7e9936a
Revises: 863d829317c8
Create Date: 2026-04-11 07:06:31.640606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8deb7e9936a'
down_revision: Union[str, None] = '863d829317c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('inspections', sa.Column('permit_url', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_inspections_permit_url'), 'inspections', ['permit_url'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_inspections_permit_url'), table_name='inspections')
    op.drop_column('inspections', 'permit_url')
