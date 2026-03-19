"""Service tier model — per-org residential service packages."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class ServiceTier(Base):
    __tablename__ = "service_tiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    base_rate: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)

    # Service inclusions
    includes_chems: Mapped[bool] = mapped_column(Boolean, default=True)
    includes_skim: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_baskets: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_vacuum: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_brush: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_equipment_check: Mapped[bool] = mapped_column(Boolean, default=False)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization", lazy="noload")
