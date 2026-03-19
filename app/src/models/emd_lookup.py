"""EMD single-lookup purchase model — tracks per-facility paid access."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class EMDLookup(Base):
    __tablename__ = "emd_lookups"
    __table_args__ = (
        UniqueConstraint("organization_id", "facility_id", name="uq_org_facility_lookup"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emd_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_cents: Mapped[int] = mapped_column(Integer, default=99)
    stripe_payment_id: Mapped[str | None] = mapped_column(String(100))
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    organization = relationship("Organization", lazy="noload")
    facility = relationship("EMDFacility", lazy="noload")
