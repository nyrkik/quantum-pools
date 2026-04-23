"""organizations.website_url — link target for the signature logo

Admin-set public website URL. Renders as the <a href> wrapper around
the signature logo when the logo is enabled. Optional; no column means
the logo ships as a static image.

Revision ID: 0002c096bcdc
Revises: 0e0abd757604
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002c096bcdc"
down_revision: Union[str, None] = "0e0abd757604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("website_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "website_url")
