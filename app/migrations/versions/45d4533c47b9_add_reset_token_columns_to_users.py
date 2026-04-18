"""add_reset_token_columns_to_users

Revision ID: 45d4533c47b9
Revises: fe4d98255aa9
Create Date: 2026-04-17 18:58:16.431530

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45d4533c47b9'
down_revision: Union[str, None] = 'fe4d98255aa9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columns may already exist from create_all on dev DBs — make idempotent.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    existing_idx = {i["name"] for i in inspector.get_indexes("users")}

    if "reset_token" not in existing_cols:
        op.add_column("users", sa.Column("reset_token", sa.String(length=255), nullable=True))
    if "reset_token_expires" not in existing_cols:
        op.add_column("users", sa.Column("reset_token_expires", sa.DateTime(timezone=True), nullable=True))
    if "ix_users_reset_token" not in existing_idx:
        op.create_index("ix_users_reset_token", "users", ["reset_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_reset_token", table_name="users")
    op.drop_column("users", "reset_token_expires")
    op.drop_column("users", "reset_token")
