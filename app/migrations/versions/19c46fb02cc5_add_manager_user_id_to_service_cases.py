"""add manager_user_id to service_cases

Revision ID: 19c46fb02cc5
Revises: 7cc81fcba9da
Create Date: 2026-04-19 06:33:12.234652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19c46fb02cc5'
down_revision: Union[str, None] = '7cc81fcba9da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Joinable FK-style column — mirrors the existing assigned_to_user_id
    # convention on the same table. Nullable: legacy cases have no user-id
    # binding, only a name string. Future code writes the id; backfill
    # populates what it can match.
    op.add_column(
        "service_cases",
        sa.Column("manager_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_service_cases_manager_user_id",
        "service_cases",
        ["manager_user_id"],
    )

    # Opportunistic backfill: match manager_name → users by
    # "first last" composition within the same org. Ambiguous or
    # unmatched names stay null.
    op.execute("""
        UPDATE service_cases sc
        SET manager_user_id = matched.user_id
        FROM (
            SELECT sc2.id AS case_id, ou.user_id
            FROM service_cases sc2
            JOIN organization_users ou ON ou.organization_id = sc2.organization_id
            JOIN users u ON u.id = ou.user_id
            WHERE sc2.manager_name IS NOT NULL
              AND sc2.manager_name = TRIM(COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,''))
        ) matched
        WHERE sc.id = matched.case_id
    """)


def downgrade() -> None:
    op.drop_index("ix_service_cases_manager_user_id", table_name="service_cases")
    op.drop_column("service_cases", "manager_user_id")
