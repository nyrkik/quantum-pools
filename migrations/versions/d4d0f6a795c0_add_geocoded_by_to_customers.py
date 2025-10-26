"""Add geocoded_by to customers

Revision ID: d4d0f6a795c0
Revises: 9f5611f8c4ff
Create Date: 2025-10-26 12:24:54.091813

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4d0f6a795c0'
down_revision: Union[str, None] = '9f5611f8c4ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add geocoded_by column to customers table
    op.add_column('customers', sa.Column('geocoded_by', sa.UUID(), nullable=True, comment='User who geocoded'))
    op.create_foreign_key('fk_customers_geocoded_by', 'customers', 'users', ['geocoded_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # Drop geocoded_by column from customers table
    op.drop_constraint('fk_customers_geocoded_by', 'customers', type_='foreignkey')
    op.drop_column('customers', 'geocoded_by')
