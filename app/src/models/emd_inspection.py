"""EMD Inspection model — individual inspection reports for a facility."""

import uuid
from datetime import datetime, timezone, date
from sqlalchemy import String, Integer, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class EMDInspection(Base):
    __tablename__ = "emd_inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emd_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # EMD data
    inspection_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    inspection_date: Mapped[date | None] = mapped_column(Date, index=True)
    inspection_type: Mapped[str | None] = mapped_column(String(50))
    inspector_name: Mapped[str | None] = mapped_column(String(100))
    total_violations: Mapped[int] = mapped_column(Integer, default=0)
    major_violations: Mapped[int] = mapped_column(Integer, default=0)
    pool_capacity_gallons: Mapped[int | None] = mapped_column(Integer)
    flow_rate_gpm: Mapped[int | None] = mapped_column(Integer)
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    report_notes: Mapped[str | None] = mapped_column(Text)
    closure_status: Mapped[str | None] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    facility = relationship("EMDFacility", back_populates="inspections", lazy="noload")
    violations = relationship("EMDViolation", back_populates="inspection", lazy="noload")
    equipment = relationship("EMDEquipment", back_populates="inspection", uselist=False, lazy="noload")
