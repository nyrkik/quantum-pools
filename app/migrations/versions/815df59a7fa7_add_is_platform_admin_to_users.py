"""add is_platform_admin to users

Revision ID: 815df59a7fa7
Revises: 19c46fb02cc5
Create Date: 2026-04-19 07:16:57.510004

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '815df59a7fa7'
down_revision: Union[str, None] = '19c46fb02cc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Platform-admin flag: distinguishes QP staff (who can execute
    # cross-org operations like CCPA purge-on-request, cross-org event
    # queries, Sonar reads) from customer-admins (whose reach stops at
    # their own org). Customer permissions continue to use the
    # OrganizationUser.role column — this flag is a separate axis.
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index(
        "ix_users_is_platform_admin",
        "users",
        ["is_platform_admin"],
        postgresql_where=sa.text("is_platform_admin = true"),
    )

    # Seed the initial platform admin. Email-based so the migration is
    # portable across environments (dev DB has the same account).
    # Missing-user is fine — indicates an empty/fresh environment.
    op.execute(
        "UPDATE users SET is_platform_admin = true "
        "WHERE email = 'brian.parrotte@pm.me'"
    )


def downgrade() -> None:
    op.drop_index("ix_users_is_platform_admin", table_name="users")
    op.drop_column("users", "is_platform_admin")
