"""ChemicalReading model — water chemistry measurements."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class ChemicalReading(Base):
    __tablename__ = "chemical_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("visits.id", ondelete="SET NULL"), index=True
    )

    # Readings
    ph: Mapped[float | None] = mapped_column(Float)
    free_chlorine: Mapped[float | None] = mapped_column(Float)
    total_chlorine: Mapped[float | None] = mapped_column(Float)
    combined_chlorine: Mapped[float | None] = mapped_column(Float)
    alkalinity: Mapped[float | None] = mapped_column(Float)
    calcium_hardness: Mapped[float | None] = mapped_column(Float)
    cyanuric_acid: Mapped[float | None] = mapped_column(Float)
    tds: Mapped[float | None] = mapped_column(Float)
    phosphates: Mapped[float | None] = mapped_column(Float)
    salt: Mapped[float | None] = mapped_column(Float)
    water_temp: Mapped[float | None] = mapped_column(Float)

    recommendations: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    property = relationship("Property", back_populates="chemical_readings", lazy="noload")
    visit = relationship("Visit", back_populates="chemical_readings", lazy="noload")
