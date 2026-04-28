"""customer portal: magic links + sessions

Revision ID: c5d0f4b33b71
Revises: 9aae5dfdf913
Create Date: 2026-04-28

Adds the two tables that back the customer-facing portal:
- customer_magic_links: short-lived single-use sign-in tokens
- customer_portal_sessions: persistent session cookies after sign-in

Both cascade on contact / customer / org deletion so deleted contacts
can't keep a live session.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d0f4b33b71"
down_revision: Union[str, None] = "9aae5dfdf913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_magic_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "contact_id",
            sa.String(length=36),
            sa.ForeignKey("customer_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.String(length=36),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_customer_magic_links_contact_id", "customer_magic_links", ["contact_id"]
    )
    op.create_index(
        "ix_customer_magic_links_customer_id", "customer_magic_links", ["customer_id"]
    )
    op.create_index(
        "ix_customer_magic_links_organization_id",
        "customer_magic_links",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_magic_links_token", "customer_magic_links", ["token"], unique=True
    )

    op.create_table(
        "customer_portal_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "contact_id",
            sa.String(length=36),
            sa.ForeignKey("customer_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.String(length=36),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_customer_portal_sessions_contact_id",
        "customer_portal_sessions",
        ["contact_id"],
    )
    op.create_index(
        "ix_customer_portal_sessions_customer_id",
        "customer_portal_sessions",
        ["customer_id"],
    )
    op.create_index(
        "ix_customer_portal_sessions_organization_id",
        "customer_portal_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_portal_sessions_token",
        "customer_portal_sessions",
        ["token"],
        unique=True,
    )
    op.create_index(
        "ix_customer_portal_sessions_expires_at",
        "customer_portal_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_portal_sessions_expires_at", table_name="customer_portal_sessions"
    )
    op.drop_index(
        "ix_customer_portal_sessions_token", table_name="customer_portal_sessions"
    )
    op.drop_index(
        "ix_customer_portal_sessions_organization_id",
        table_name="customer_portal_sessions",
    )
    op.drop_index(
        "ix_customer_portal_sessions_customer_id",
        table_name="customer_portal_sessions",
    )
    op.drop_index(
        "ix_customer_portal_sessions_contact_id",
        table_name="customer_portal_sessions",
    )
    op.drop_table("customer_portal_sessions")

    op.drop_index(
        "ix_customer_magic_links_token", table_name="customer_magic_links"
    )
    op.drop_index(
        "ix_customer_magic_links_organization_id", table_name="customer_magic_links"
    )
    op.drop_index(
        "ix_customer_magic_links_customer_id", table_name="customer_magic_links"
    )
    op.drop_index(
        "ix_customer_magic_links_contact_id", table_name="customer_magic_links"
    )
    op.drop_table("customer_magic_links")
