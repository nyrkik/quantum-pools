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
    # Sacramento County's Establishment ID (e.g. FA0005473). NOT unique on
    # its own — a single establishment can have multiple inspection_facilities
    # rows distinguished by `program_identifier` (e.g. one establishment with
    # buildings at two addresses, or with separate POOL and SPA permits).
    # The composite uniqueness `(facility_id, program_identifier) NULLS NOT
    # DISTINCT` is enforced by `ix_inspection_facilities_fa_program_unique`
    # (see migration 3a8f1c7e2b40).
    facility_id: Mapped[str | None] = mapped_column(String(50), index=True)
    permit_holder: Mapped[str | None] = mapped_column(String(255))
    facility_type: Mapped[str | None] = mapped_column(String(50))
    # Program / building / body-of-water discriminator within an establishment.
    # Set to the inspection's program_identifier value (e.g. "POOL", "SPA",
    # "POOL @ 4440 OAK HOLLOW DR"). Multiple facility rows can share an FA
    # only if their program_identifier values differ.
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
