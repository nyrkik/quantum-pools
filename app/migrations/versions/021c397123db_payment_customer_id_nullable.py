"""payment customer_id nullable

Revision ID: 021c397123db
Revises: e28ae01d6ba5
Create Date: 2026-04-07 11:16:03.688036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '021c397123db'
down_revision: Union[str, None] = 'e28ae01d6ba5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('payments', 'customer_id', existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    op.alter_column('payments', 'customer_id', existing_type=sa.String(36), nullable=False)
