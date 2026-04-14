"""drop email_auto_send_enabled from organizations (auto-send removed)

Revision ID: 2d1e5fa92f88
Revises: f5b2c3d4e5f6
Create Date: 2026-04-14 03:34:25.537704

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d1e5fa92f88'
down_revision: Union[str, None] = 'f5b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('organizations', 'email_auto_send_enabled')


def downgrade() -> None:
    op.add_column(
        'organizations',
        sa.Column(
            'email_auto_send_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
