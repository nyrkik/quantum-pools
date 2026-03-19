"""Feature catalog and tier models for à la carte subscriptions."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(100))
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    billing_type: Mapped[str] = mapped_column(String(20), default="recurring")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tiers = relationship("FeatureTier", back_populates="feature", lazy="noload")
    subscriptions = relationship("OrgSubscription", back_populates="feature", lazy="noload")


class FeatureTier(Base):
    __tablename__ = "feature_tiers"
    __table_args__ = (
        UniqueConstraint("feature_id", "slug", name="uq_feature_tier_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    feature_id: Mapped[str] = mapped_column(String(36), ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(100))
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    billing_type: Mapped[str] = mapped_column(String(20), default="recurring")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    feature = relationship("Feature", back_populates="tiers", lazy="noload")
