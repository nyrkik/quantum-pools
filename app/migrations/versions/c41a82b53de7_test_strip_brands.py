"""test_strip_brands + test_strip_pads — chart library for vision-driven reads

Stores per-brand pad layouts and color → value scales so the test-strip
reader can do ground-truth color matching instead of relying on Claude's
recall of brand color charts. Each brand has N pads; each pad maps to one
chemistry field with an ordered list of (color_hex, measurement_value)
points. The reader injects this scale into the Vision prompt for the
matched brand.

Both tables are reference data (not org-scoped) — the same AquaChek strip
reads the same way for every customer. Aliases are stored to handle the
"AquaChek 7-way" vs. "AquaChek 7-Way Pool Test Strips" variance.

Revision ID: c41a82b53de7
Revises: 8fa204c1d3b6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c41a82b53de7"
down_revision: Union[str, None] = "8fa204c1d3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_strip_brands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("manufacturer", sa.String(150)),
        sa.Column("num_pads", sa.Integer, nullable=False),
        sa.Column("aliases", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("source_url", sa.String(500)),
        sa.Column("notes", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_test_strip_brands_name", "test_strip_brands", ["name"])

    op.create_table(
        "test_strip_pads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36),
                  sa.ForeignKey("test_strip_brands.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("pad_index", sa.Integer, nullable=False),
        sa.Column("chemistry_field", sa.String(50), nullable=False),
        # color_scale: ordered list of {value: float, hex: "#RRGGBB"} dicts,
        # lowest value first.
        sa.Column("color_scale", sa.JSON, nullable=False),
        sa.Column("unit", sa.String(20)),
        sa.Column("notes", sa.Text),
        sa.UniqueConstraint("brand_id", "pad_index", name="uq_test_strip_pads_brand_index"),
    )
    op.create_index(
        "ix_test_strip_pads_brand", "test_strip_pads", ["brand_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_test_strip_pads_brand", "test_strip_pads")
    op.drop_table("test_strip_pads")
    op.drop_index("ix_test_strip_brands_name", "test_strip_brands")
    op.drop_table("test_strip_brands")
