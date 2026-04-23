"""per-user email sign-off (valediction)

Optional lead-in line rendered between the email body and the auto-prepended
name. Per-user because style is personal ("Best," vs "v/r," vs none).

Revision ID: d8bbff647e8b
Revises: fd7cd2e9767a
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8bbff647e8b"
down_revision: Union[str, None] = "fd7cd2e9767a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_users",
        sa.Column("email_signoff", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_users", "email_signoff")
