"""Create email_integrations table for multi-mode email per org

Phase 5b.1 of docs/email-integrations-plan.md. Adds the foundation that
lets each organization (and within an org, each connected user account)
specify its own email integration mode — managed, gmail_api, ms_graph,
forwarding, or manual.

Revision ID: c4b7e9f1a230
Revises: 3a8f1c7e2b40
Create Date: 2026-04-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4b7e9f1a230"
down_revision: Union[str, None] = "3a8f1c7e2b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_integrations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="setup_required"),
        sa.Column("account_email", sa.String(length=255), nullable=True),
        sa.Column("inbound_sender_address", sa.String(length=255), nullable=True),
        sa.Column("outbound_provider", sa.String(length=20), nullable=False, server_default="postmark"),
        sa.Column("config_encrypted", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_history_id", sa.String(length=50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_email_integrations_organization_id",
        "email_integrations",
        ["organization_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_email_integrations_org_account",
        "email_integrations",
        ["organization_id", "account_email"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_email_integrations_org_account", "email_integrations", type_="unique")
    op.drop_index("ix_email_integrations_organization_id", table_name="email_integrations")
    op.drop_table("email_integrations")
