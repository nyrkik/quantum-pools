"""Bather load jurisdiction model — calculation methods by US jurisdiction."""

import uuid
import enum
from sqlalchemy import String, Boolean, Float, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class JurisdictionMethod(str, enum.Enum):
    california = "california"
    ispsc = "ispsc"
    mahc = "mahc"
    texas = "texas"
    florida = "florida"
    arizona = "arizona"
    new_york = "new_york"
    georgia = "georgia"
    north_carolina = "north_carolina"
    illinois = "illinois"


class BatherLoadJurisdiction(Base):
    __tablename__ = "bather_load_jurisdictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    method_key: Mapped[JurisdictionMethod] = mapped_column(Enum(JurisdictionMethod), nullable=False, unique=True)

    shallow_sqft_per_bather: Mapped[float] = mapped_column(Float, nullable=False)
    deep_sqft_per_bather: Mapped[float] = mapped_column(Float, nullable=False)
    spa_sqft_per_bather: Mapped[float] = mapped_column(Float, default=10.0)
    diving_sqft_per_board: Mapped[float] = mapped_column(Float, default=300.0)

    has_deck_bonus: Mapped[bool] = mapped_column(Boolean, default=False)
    deck_sqft_per_bather: Mapped[float | None] = mapped_column(Float)

    has_flow_rate_test: Mapped[bool] = mapped_column(Boolean, default=False)
    flow_gpm_per_bather: Mapped[float | None] = mapped_column(Float)

    has_indoor_multiplier: Mapped[bool] = mapped_column(Boolean, default=False)
    indoor_multiplier: Mapped[float | None] = mapped_column(Float)

    has_limited_use_multiplier: Mapped[bool] = mapped_column(Boolean, default=False)
    limited_use_multiplier: Mapped[float | None] = mapped_column(Float)

    depth_based: Mapped[bool] = mapped_column(Boolean, default=True)
    depth_break_ft: Mapped[float] = mapped_column(Float, default=5.0)

    notes: Mapped[str | None] = mapped_column(Text)
