"""Create organization_users table

Revision ID: 9f5611f8c4ff
Revises: 9b1d3e95633e
Create Date: 2025-10-26 11:26:27.507100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f5611f8c4ff'
down_revision: Union[str, None] = '9b1d3e95633e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
