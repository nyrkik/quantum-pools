"""Visit model — a scheduled or completed service stop."""

import uuid
import enum
from datetime import datetime, timezone, date
from sqlalchemy import String, Boolean, DateTime, Date, Text, Integer, Float, ForeignKey, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class VisitStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tech_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("techs.id", ondelete="SET NULL"), index=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    service_day: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default=VisitStatus.scheduled.value)
    actual_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    service_performed: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="visits", lazy="noload")
    tech = relationship("Tech", back_populates="visits", lazy="noload")
    visit_services = relationship("VisitService", back_populates="visit", lazy="noload")
    chemical_readings = relationship("ChemicalReading", back_populates="visit", lazy="noload")
