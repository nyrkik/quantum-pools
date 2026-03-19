"""Organization subscription model — tracks which features each org has purchased."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class OrgSubscription(Base):
    __tablename__ = "org_subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", "feature_id", "feature_tier_id", name="uq_org_feature_tier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_tier_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("feature_tiers.id", ondelete="CASCADE"), nullable=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))
    stripe_status: Mapped[str] = mapped_column(String(20), default="active")
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", lazy="noload")
    feature = relationship("Feature", back_populates="subscriptions", lazy="noload")
    feature_tier = relationship("FeatureTier", lazy="noload")
