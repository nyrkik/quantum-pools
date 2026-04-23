"""signature composition columns

- organizations.auto_signature_prefix: admin toggle. When true, outbound
  signature gets `{sender_first_name}\\n{org_name}\\n` prepended before the
  user's signature text. Default true preserves existing behavior.
- organizations.include_logo_in_signature: admin toggle. When true AND
  organization.logo_url is set, HTML signature includes a CID-inlined
  logo at the bottom. Default false.
- organization_users.email_signature: per-user tail text (phone, title,
  etc.). Falls back to organizations.agent_signature when null.

Revision ID: fd7cd2e9767a
Revises: a66dd480ab1b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fd7cd2e9767a"
down_revision: Union[str, None] = "a66dd480ab1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "auto_signature_prefix",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "include_logo_in_signature",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "organization_users",
        sa.Column("email_signature", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_users", "email_signature")
    op.drop_column("organizations", "include_logo_in_signature")
    op.drop_column("organizations", "auto_signature_prefix")
