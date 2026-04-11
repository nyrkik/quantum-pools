"""EMD Inspection model — individual inspection reports for a facility."""

import uuid
from datetime import datetime, timezone, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspection_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # EMD data
    inspection_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    inspection_date: Mapped[date | None] = mapped_column(Date, index=True)
    inspection_type: Mapped[str | None] = mapped_column(String(50))
    inspector_name: Mapped[str | None] = mapped_column(String(100))
    co_inspector: Mapped[str | None] = mapped_column(String(100))
    inspector_phone: Mapped[str | None] = mapped_column(String(50))
    program_identifier: Mapped[str | None] = mapped_column(String(100))
    permit_id: Mapped[str | None] = mapped_column(String(50), index=True)
    # Portal permit page URL (e.g. /sacramento/program-rec-health/permit/?permitID=<UUID>)
    # — captured from date scrapes so we can walk permits directly to find inspections
    # the date-search listing collapses (multi-BoW per facility/day).
    permit_url: Mapped[str | None] = mapped_column(String(500), index=True)
    total_violations: Mapped[int] = mapped_column(Integer, default=0)
    major_violations: Mapped[int] = mapped_column(Integer, default=0)
    pool_capacity_gallons: Mapped[int | None] = mapped_column(Integer)
    flow_rate_gpm: Mapped[int | None] = mapped_column(Integer)
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    report_notes: Mapped[str | None] = mapped_column(Text)
    closure_status: Mapped[str | None] = mapped_column(String(50))
    closure_required: Mapped[bool] = mapped_column(Boolean, default=False)
    reinspection_required: Mapped[bool] = mapped_column(Boolean, default=False)
    water_chemistry: Mapped[dict | None] = mapped_column(JSON)
    pdf_download_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pdf_permanently_missing: Mapped[bool] = mapped_column(Boolean, default=False)

    # Gauge readings (from chemistry/readings page)
    pool_spa_temp: Mapped[float | None] = mapped_column(Integer)
    rp_gauge: Mapped[float | None] = mapped_column(Integer)
    rv_gauge: Mapped[float | None] = mapped_column(Integer)
    bp_gauge: Mapped[float | None] = mapped_column(Integer)
    bv_gauge: Mapped[float | None] = mapped_column(Integer)
    uv_output: Mapped[str | None] = mapped_column(String(50))

    # Sign-off
    accepted_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    @property
    def has_pdf(self) -> bool:
        return bool(self.pdf_path and not self.pdf_path.startswith("/mnt"))

    # Relationships
    facility = relationship("InspectionFacility", back_populates="inspections", lazy="noload")
    violations = relationship("InspectionViolation", back_populates="inspection", lazy="noload")
    equipment = relationship("InspectionEquipment", back_populates="inspection", uselist=False, lazy="noload")
