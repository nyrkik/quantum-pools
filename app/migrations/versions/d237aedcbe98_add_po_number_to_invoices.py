"""add po_number to invoices

FB-56: customers send a PO# AFTER approving the estimate, and the
current workflow forces a re-open + re-approve round-trip just to
record it (which loses the original approval timestamp). New column
lets PO# be patched independently of approval state.

Indexed because PO# is the customer-side reference for cross-system
matching (their AP system filters by PO).

Revision ID: d237aedcbe98
Revises: 37a7d49f43d8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d237aedcbe98"
down_revision: Union[str, None] = "37a7d49f43d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("po_number", sa.String(50), nullable=True),
    )
    op.create_index(
        "ix_invoices_po_number", "invoices", ["po_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_po_number", table_name="invoices")
    op.drop_column("invoices", "po_number")
