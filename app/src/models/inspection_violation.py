"""EMD Violation model — individual violations from an inspection report."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class InspectionViolation(Base):
    __tablename__ = "inspection_violations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspection_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    violation_code: Mapped[str | None] = mapped_column(String(20))
    violation_title: Mapped[str | None] = mapped_column(String(500))
    observations: Mapped[str | None] = mapped_column(Text)
    corrective_action: Mapped[str | None] = mapped_column(Text)
    is_major_violation: Mapped[bool] = mapped_column(Boolean, default=False)
    severity_level: Mapped[str | None] = mapped_column(String(20))
    shorthand_summary: Mapped[str | None] = mapped_column(String(500))
    code_description: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    inspection = relationship("Inspection", back_populates="violations", lazy="noload")
    facility = relationship("InspectionFacility", lazy="noload")
