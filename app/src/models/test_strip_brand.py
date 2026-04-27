"""Test strip brand registry — chart library for the vision reader.

`TestStripBrand` is one row per brand+model (e.g. "AquaChek 7-way Pool"). It
owns multiple `TestStripPad` rows, one per colored pad on the strip, in
display order (`pad_index` 0..N-1). Each pad maps to one chemistry field
with a `color_scale` ladder of (value, hex) tuples — the reference scale
printed on the bottle.

Both tables are reference data, not org-scoped — same strip reads the same
for every customer.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, JSON, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class TestStripBrand(Base):
    __tablename__ = "test_strip_brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150))
    num_pads: Mapped[int] = mapped_column(Integer, nullable=False)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    pads: Mapped[list["TestStripPad"]] = relationship(
        "TestStripPad", back_populates="brand", cascade="all, delete-orphan", lazy="noload",
        order_by="TestStripPad.pad_index",
    )


class TestStripPad(Base):
    __tablename__ = "test_strip_pads"
    __table_args__ = (UniqueConstraint("brand_id", "pad_index", name="uq_test_strip_pads_brand_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_strip_brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pad_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chemistry_field: Mapped[str] = mapped_column(String(50), nullable=False)
    # color_scale: ordered list of {"value": float, "hex": "#RRGGBB"}.
    color_scale: Mapped[list] = mapped_column(JSON, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    brand: Mapped["TestStripBrand"] = relationship("TestStripBrand", back_populates="pads", lazy="noload")
