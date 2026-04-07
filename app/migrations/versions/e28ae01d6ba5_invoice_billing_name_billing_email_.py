"""invoice billing_name billing_email nullable customer_id

Revision ID: e28ae01d6ba5
Revises: d5c2e1f97a84
Create Date: 2026-04-07 09:59:54.046204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e28ae01d6ba5'
down_revision: Union[str, None] = 'd5c2e1f97a84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('billing_name', sa.String(200), nullable=True))
    op.add_column('invoices', sa.Column('billing_email', sa.String(255), nullable=True))
    op.alter_column('invoices', 'customer_id', existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    op.alter_column('invoices', 'customer_id', existing_type=sa.String(36), nullable=False)
    op.drop_column('invoices', 'billing_email')
    op.drop_column('invoices', 'billing_name')
