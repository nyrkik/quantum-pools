"""Allow multiple inspection_facility rows per FA, distinguished by program_identifier

This unblocks the multi-building case (e.g. Arbor Ridge: one EMD permit
FA0005473 covers two physical buildings 4407 and 4440 Oak Hollow Dr, with
inspections distinguished by program_identifier values like
'POOL @ 4440 OAK HOLLOW DR'). Same pattern handles POOL/SPA discriminators
at single-address establishments.

Schema change:
  - Drop the unique index on facility_id (single-column)
  - Add a non-unique index on facility_id (so lookups by FA stay fast)
  - Add a composite unique index on (facility_id, program_identifier)
    using NULLS NOT DISTINCT (Postgres 15+) so that a single NULL
    program_identifier still uniques per FA.

Revision ID: 3a8f1c7e2b40
Revises: e8deb7e9936a
Create Date: 2026-04-11 09:30:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "3a8f1c7e2b40"
down_revision: Union[str, None] = "e8deb7e9936a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing single-column unique index on facility_id
    op.drop_index("ix_inspection_facilities_facility_id", table_name="inspection_facilities")
    # Recreate as non-unique (lookups by FA still need to be fast)
    op.create_index(
        "ix_inspection_facilities_facility_id",
        "inspection_facilities",
        ["facility_id"],
        unique=False,
    )
    # New composite unique index. Uses NULLS NOT DISTINCT (PG15+) so that
    # NULL program_identifier counts as a single value per FA.
    op.execute(
        "CREATE UNIQUE INDEX ix_inspection_facilities_fa_program_unique "
        "ON inspection_facilities (facility_id, program_identifier) "
        "NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inspection_facilities_fa_program_unique")
    op.drop_index("ix_inspection_facilities_facility_id", table_name="inspection_facilities")
    op.create_index(
        "ix_inspection_facilities_facility_id",
        "inspection_facilities",
        ["facility_id"],
        unique=True,
    )
