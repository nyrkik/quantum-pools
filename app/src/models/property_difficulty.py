"""Property difficulty model — measured and scored factors for profitability analysis."""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, Integer, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class ShadeExposure(str, enum.Enum):
    full_sun = "full_sun"
    partial_shade = "partial_shade"
    full_shade = "full_shade"


class TreeDebrisLevel(str, enum.Enum):
    none = "none"
    low = "low"
    moderate = "moderate"
    heavy = "heavy"


class EnclosureType(str, enum.Enum):
    open = "open"
    screened = "screened"
    indoor = "indoor"


class PropertyDifficulty(Base):
    __tablename__ = "property_difficulties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Measured fields (auto-calculated or entered)
    shallow_sqft: Mapped[float | None] = mapped_column(Float)
    deep_sqft: Mapped[float | None] = mapped_column(Float)
    has_deep_end: Mapped[bool] = mapped_column(Boolean, default=False)
    spa_sqft: Mapped[float | None] = mapped_column(Float)
    diving_board_count: Mapped[int] = mapped_column(Integer, default=0)
    pump_flow_gpm: Mapped[float | None] = mapped_column(Float)
    is_indoor: Mapped[bool] = mapped_column(Boolean, default=False)
    equipment_age_years: Mapped[int | None] = mapped_column(Integer)
    shade_exposure: Mapped[ShadeExposure | None] = mapped_column(Enum(ShadeExposure))
    tree_debris_level: Mapped[TreeDebrisLevel | None] = mapped_column(Enum(TreeDebrisLevel))
    enclosure_type: Mapped[EnclosureType | None] = mapped_column(Enum(EnclosureType))
    chem_feeder_type: Mapped[str | None] = mapped_column(String(50))

    # Scored fields (user rates 1-5)
    access_difficulty_score: Mapped[float] = mapped_column(Float, default=1.0)
    customer_demands_score: Mapped[float] = mapped_column(Float, default=1.0)
    chemical_demand_score: Mapped[float] = mapped_column(Float, default=1.0)
    callback_frequency_score: Mapped[float] = mapped_column(Float, default=1.0)

    # Override
    override_composite: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="difficulty", lazy="noload")
    organization = relationship("Organization", lazy="noload")
