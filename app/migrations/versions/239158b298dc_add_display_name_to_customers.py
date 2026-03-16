"""add display_name to customers

Revision ID: 239158b298dc
Revises: a687ed61964e
Create Date: 2026-03-16 04:44:18.458651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '239158b298dc'
down_revision: Union[str, None] = 'a687ed61964e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('display_name', sa.String(200), nullable=True))
    op.create_index('ix_customers_display_name', 'customers', ['display_name'])

    # Backfill: commercial = first_name, residential = first_name || ' ' || last_name
    op.execute("""
        UPDATE customers
        SET display_name = CASE
            WHEN customer_type = 'commercial' THEN TRIM(first_name)
            ELSE TRIM(first_name || ' ' || last_name)
        END
    """)


def downgrade() -> None:
    op.drop_index('ix_customers_display_name', 'customers')
    op.drop_column('customers', 'display_name')
