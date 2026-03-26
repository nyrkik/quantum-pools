"""VisitPhoto model — structured photo storage for visits."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class VisitPhoto(Base):
    __tablename__ = "visit_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    water_feature_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("water_features.id", ondelete="SET NULL"), index=True
    )
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(20))  # before, after, equipment, issue, debris
    caption: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    visit = relationship("Visit", back_populates="photos_rel", lazy="noload")
    water_feature = relationship("WaterFeature", lazy="noload")
    organization = relationship("Organization", lazy="noload")
