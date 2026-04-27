"""parsed_payments table + payments.source_message_id

Phase 1 of payment reconciliation. New `parsed_payments` table holds
structured-extraction output keyed by source AgentMessage so parser
runs can re-execute without losing data. New
`payments.source_message_id` column carries the audit-trail link from
each Payment back to the email that produced it.

See `docs/payment-reconciliation-spec.md` §3.

Revision ID: 37a7d49f43d8
Revises: 4f33fd7976c0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "37a7d49f43d8"
down_revision: Union[str, None] = "4f33fd7976c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "parsed_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_message_id", sa.String(36),
            sa.ForeignKey("agent_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("processor", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("payer_name", sa.String(255), nullable=True),
        sa.Column("property_hint", sa.String(255), nullable=True),
        sa.Column("invoice_hint", sa.String(100), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("payment_date", sa.Date, nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("raw_block", sa.Text, nullable=True),
        sa.Column("match_status", sa.String(20), nullable=False, server_default="unmatched"),
        sa.Column(
            "matched_invoice_id", sa.String(36),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "payment_id", sa.String(36),
            sa.ForeignKey("payments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column("match_reasoning", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_parsed_payments_org_status",
        "parsed_payments",
        ["organization_id", "match_status"],
    )
    op.create_index(
        "ix_parsed_payments_message",
        "parsed_payments",
        ["agent_message_id"],
    )
    op.create_index(
        "ix_parsed_payments_processor",
        "parsed_payments",
        ["processor"],
    )

    op.add_column(
        "payments",
        sa.Column(
            "source_message_id", sa.String(36),
            sa.ForeignKey("agent_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_payments_source_message",
        "payments",
        ["source_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payments_source_message", table_name="payments")
    op.drop_column("payments", "source_message_id")
    op.drop_index("ix_parsed_payments_processor", table_name="parsed_payments")
    op.drop_index("ix_parsed_payments_message", table_name="parsed_payments")
    op.drop_index("ix_parsed_payments_org_status", table_name="parsed_payments")
    op.drop_table("parsed_payments")
