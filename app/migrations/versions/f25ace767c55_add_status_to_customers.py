"""add_status_to_customers

Revision ID: f25ace767c55
Revises: 730d40939df1
Create Date: 2026-03-14 06:27:07.210503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f25ace767c55'
down_revision: Union[str, None] = '730d40939df1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('status', sa.String(length=20), server_default='active', nullable=False))
    # Backfill: inactive customers get status='inactive'
    op.execute("UPDATE customers SET status = 'inactive' WHERE is_active = false")


def downgrade() -> None:
    op.drop_column('customers', 'status')
