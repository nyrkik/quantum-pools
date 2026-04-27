"""equipment_items.source_inspection_id + source_slot for inspection-derived items

Adds two nullable columns to `equipment_items` that let us auto-populate from
inspection PDF data without losing track of provenance:

- `source_inspection_id` — FK to `inspections.id`. Lets the UI render a
  "from inspection" badge and lets the sync routine re-run idempotently.
- `source_slot` — opaque string identifying which InspectionEquipment field
  produced the row (e.g. `filter_pump_2`, `sanitizer_1`, `main_drain`).
  Combined with `(water_feature_id, source_inspection_id)` this is the
  upsert key for re-parses.

Both nullable: manually-entered equipment_items remain valid and have NULL
in both columns. The sync routine leaves manual rows alone — it only touches
rows where `source_inspection_id IS NOT NULL`.

Revision ID: 8fa204c1d3b6
Revises: e6a3f4d12c89
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8fa204c1d3b6"
down_revision: Union[str, None] = "e6a3f4d12c89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "equipment_items",
        sa.Column("source_inspection_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "equipment_items",
        sa.Column("source_slot", sa.String(50), nullable=True),
    )
    op.create_foreign_key(
        "fk_equipment_items_source_inspection",
        "equipment_items",
        "inspections",
        ["source_inspection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_equipment_items_source_inspection",
        "equipment_items",
        ["source_inspection_id"],
        postgresql_where=sa.text("source_inspection_id IS NOT NULL"),
    )
    # Composite index for the upsert lookup
    op.create_index(
        "ix_equipment_items_source_dedup",
        "equipment_items",
        ["water_feature_id", "source_inspection_id", "source_slot"],
        postgresql_where=sa.text("source_inspection_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_equipment_items_source_dedup", "equipment_items")
    op.drop_index("ix_equipment_items_source_inspection", "equipment_items")
    op.drop_constraint("fk_equipment_items_source_inspection", "equipment_items", type_="foreignkey")
    op.drop_column("equipment_items", "source_slot")
    op.drop_column("equipment_items", "source_inspection_id")
