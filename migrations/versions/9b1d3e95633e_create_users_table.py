"""Create users table

Revision ID: 9b1d3e95633e
Revises: fea82661d512
Create Date: 2025-10-26 11:25:57.618902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1d3e95633e'
down_revision: Union[str, None] = 'fea82661d512'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
