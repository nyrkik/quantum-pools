"""drop org_cost_settings.late_fee_pct

Revision ID: f2d3b5e6c703
Revises: e1f2a4c5d602
Create Date: 2026-04-29

The legacy `org_cost_settings.late_fee_pct` was display-only boilerplate
on estimate-approval pages ("Late fee: 1.5% / month"). It never drove
any actual fee application. With Phase 8, the late-fee policy lives on
the Organization model (`late_fee_enabled/type/amount/grace_days/minimum`)
and is the single source of truth — both for `BillingService.run_late_fees`
(actual application) and for `BillingService.late_fee_clause` (the
customer-facing sentence on estimates).

This migration drops the duplicate. All 4 backend reads + 1 frontend
template + 1 Settings input were ported to use the derived clause in
the same commit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2d3b5e6c703"
down_revision: Union[str, None] = "e1f2a4c5d602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("org_cost_settings", "late_fee_pct")


def downgrade() -> None:
    op.add_column(
        "org_cost_settings",
        sa.Column(
            "late_fee_pct",
            sa.Float(),
            nullable=False,
            server_default="1.5",
        ),
    )
