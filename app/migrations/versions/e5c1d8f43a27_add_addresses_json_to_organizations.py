"""Add addresses JSON to organizations

Revision ID: e5c1d8f43a27
Revises: d4b9c7e32f15
Create Date: 2026-04-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5c1d8f43a27'
down_revision: str = 'd4b9c7e32f15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('addresses', sa.Text(), nullable=True))
    # Backfill from existing flat fields
    op.execute("""
        UPDATE organizations
        SET addresses = json_build_object(
            'mailing', json_build_object(
                'street', COALESCE(address, ''),
                'city', COALESCE(city, ''),
                'state', COALESCE(state, ''),
                'zip', COALESCE(zip_code, '')
            ),
            'physical', json_build_object('same_as', 'mailing'),
            'billing', json_build_object('same_as', 'mailing')
        )::text
        WHERE address IS NOT NULL AND address != ''
    """)


def downgrade() -> None:
    op.drop_column('organizations', 'addresses')
