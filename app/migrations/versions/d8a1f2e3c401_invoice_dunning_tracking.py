"""invoice dunning tracking

Revision ID: d8a1f2e3c401
Revises: c5d0f4b33b71
Create Date: 2026-04-28

Tracks where each invoice is in the dunning sequence (T+0/3/7/14).
- last_dunning_step_sent: 0 = none yet, 1-4 = which step was last sent.
  Step 4 is the "service at risk" final notice; an invoice with
  step_sent >= 4 is the "service-at-risk" set the owner reviews.
- last_dunning_sent_at: when the last step fired. Used to gate the next
  step against the cadence + as a sanity check on the per-day scheduler.

Defaults to 0 / NULL on every existing row — they enter the sequence
the first time the daily scheduler sees them past-due with balance > 0.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8a1f2e3c401"
down_revision: Union[str, None] = "c5d0f4b33b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column(
            "last_dunning_step_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "last_dunning_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("invoices", "last_dunning_sent_at")
    op.drop_column("invoices", "last_dunning_step_sent")
