"""add internal_notes to invoices

Revision ID: fe4d98255aa9
Revises: dc6f8f089df6
Create Date: 2026-04-16 19:58:07.633618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fe4d98255aa9'
down_revision: Union[str, None] = 'dc6f8f089df6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('internal_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('invoices', 'internal_notes')
