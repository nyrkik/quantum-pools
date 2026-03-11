"""Property jurisdiction model — links properties to bather load jurisdictions."""

import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class PropertyJurisdiction(Base):
    __tablename__ = "property_jurisdictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    jurisdiction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bather_load_jurisdictions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    property = relationship("Property", back_populates="jurisdiction", lazy="noload")
    jurisdiction = relationship("BatherLoadJurisdiction", lazy="joined")
    organization = relationship("Organization", lazy="noload")
