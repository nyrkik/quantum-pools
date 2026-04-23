"""organizations.allow_per_user_signature toggle

When false, send path ignores the per-user email_signature / email_signoff
columns and sends with only the org's shared settings. Lever for orgs
that want absolute signature consistency across all senders.

Default true preserves current behavior.

Revision ID: 0e0abd757604
Revises: d8bbff647e8b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0e0abd757604"
down_revision: Union[str, None] = "d8bbff647e8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "allow_per_user_signature",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "allow_per_user_signature")
