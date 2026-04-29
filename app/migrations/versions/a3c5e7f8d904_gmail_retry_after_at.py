"""gmail rate-limit parking — persist retry-after across all Gmail paths

Revision ID: a3c5e7f8d904
Revises: f2d3b5e6c703
Create Date: 2026-04-29

The 2026-04-28 user-rate-limit lockout exposed three holes beyond the
poller fix: outbound `send_reply` and the read/spam mirror had no
Retry-After awareness, and the poller's in-memory parking dict was lost
on restart. A single column on email_integrations gives every Gmail
code path a shared "park until T" signal that survives restart.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c5e7f8d904"
down_revision: Union[str, None] = "f2d3b5e6c703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_integrations",
        sa.Column(
            "gmail_retry_after_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("email_integrations", "gmail_retry_after_at")
