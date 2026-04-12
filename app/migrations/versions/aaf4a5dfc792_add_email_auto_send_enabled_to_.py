"""add email_auto_send_enabled to organizations

Revision ID: aaf4a5dfc792
Revises: c4b7e9f1a230
Create Date: 2026-04-12 06:19:07.238609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'aaf4a5dfc792'
down_revision: Union[str, None] = 'c4b7e9f1a230'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column(
        'email_auto_send_enabled', sa.Boolean(),
        nullable=False, server_default=sa.text('false'),
    ))


def downgrade() -> None:
    op.drop_column('organizations', 'email_auto_send_enabled')
