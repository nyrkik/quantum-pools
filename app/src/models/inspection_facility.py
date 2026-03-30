"""EMD Facility model — Sacramento County health department facility records."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class InspectionFacility(Base):
    __tablename__ = "inspection_facilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Facility info from EMD website
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    street_address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(50), default="CA")
    zip_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(50))
    facility_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    permit_holder: Mapped[str | None] = mapped_column(String(255))
    facility_type: Mapped[str | None] = mapped_column(String(50))
    program_identifier: Mapped[str | None] = mapped_column(String(100))

    # Link to our customer/property
    matched_property_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    inspections = relationship("Inspection", back_populates="facility", lazy="noload")
    matched_property = relationship("Property", lazy="noload")
    organization = relationship("Organization", lazy="noload")
