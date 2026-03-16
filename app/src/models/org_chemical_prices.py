"""Organization chemical price overrides — user's actual prices per org."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class OrgChemicalPrices(Base):
    __tablename__ = "org_chemical_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # User's actual prices (null = use regional default)
    liquid_chlorine_per_gal: Mapped[float | None] = mapped_column(Float)
    tabs_per_bucket: Mapped[float | None] = mapped_column(Float)  # 50lb bucket
    cal_hypo_per_lb: Mapped[float | None] = mapped_column(Float)
    dichlor_per_lb: Mapped[float | None] = mapped_column(Float)
    salt_per_bag: Mapped[float | None] = mapped_column(Float)  # 40lb bag
    acid_per_gal: Mapped[float | None] = mapped_column(Float)
    cya_per_lb: Mapped[float | None] = mapped_column(Float)
    bromine_per_lb: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization", lazy="noload")
