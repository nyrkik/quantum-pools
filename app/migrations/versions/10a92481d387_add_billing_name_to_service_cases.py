"""Add billing_name to service_cases

Revision ID: 10a92481d387
Revises: 021c397123db
Create Date: 2026-04-08 14:05:47.920625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '10a92481d387'
down_revision: Union[str, None] = '021c397123db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('service_cases', sa.Column('billing_name', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('service_cases', 'billing_name')
