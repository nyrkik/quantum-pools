"""late fees + property holds (Phase 8)

Revision ID: e1f2a4c5d602
Revises: d8a1f2e3c401
Create Date: 2026-04-29

Adds the org/customer columns that drive late-fee application, plus the
new property_holds table that lets recurring billing skip a property
during winterization, vacation, etc.

Late-fee config lives on Organization (org-wide policy) with an optional
per-Customer override (`late_fee_override_enabled`: null=inherit,
true/false=force). Late fees are applied as separate InvoiceLineItem
rows on the past-due invoice (no schema change to invoice_line_items).

Service holds are date-range rows scoped to a property; recurring
billing skips a property if any hold is active on the billing period
start date.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a4c5d602"
down_revision: Union[str, None] = "d8a1f2e3c401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "late_fee_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("late_fee_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("late_fee_amount", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "late_fee_grace_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("late_fee_minimum", sa.Numeric(10, 2), nullable=True),
    )

    op.add_column(
        "customers",
        sa.Column("late_fee_override_enabled", sa.Boolean(), nullable=True),
    )

    op.create_table(
        "property_holds",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "property_id",
            sa.String(length=36),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_property_holds_property_id", "property_holds", ["property_id"]
    )
    op.create_index(
        "ix_property_holds_organization_id",
        "property_holds",
        ["organization_id"],
    )
    op.create_index(
        "ix_property_holds_dates",
        "property_holds",
        ["property_id", "start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_property_holds_dates", table_name="property_holds")
    op.drop_index(
        "ix_property_holds_organization_id", table_name="property_holds"
    )
    op.drop_index("ix_property_holds_property_id", table_name="property_holds")
    op.drop_table("property_holds")

    op.drop_column("customers", "late_fee_override_enabled")

    op.drop_column("organizations", "late_fee_minimum")
    op.drop_column("organizations", "late_fee_grace_days")
    op.drop_column("organizations", "late_fee_amount")
    op.drop_column("organizations", "late_fee_type")
    op.drop_column("organizations", "late_fee_enabled")
