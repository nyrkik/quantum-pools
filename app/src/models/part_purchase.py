"""PartPurchase — actual cost records per org."""

import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, Float, Integer, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class PartPurchase(Base):
    __tablename__ = "part_purchases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    catalog_part_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("parts_catalog.id", ondelete="SET NULL")
    )
    sku: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    markup_pct: Mapped[float | None] = mapped_column(Float)
    customer_price: Mapped[float | None] = mapped_column(Float)

    visit_charge_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("visit_charges.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="SET NULL"), index=True
    )
    property_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("properties.id", ondelete="SET NULL"), index=True
    )
    water_feature_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("water_features.id", ondelete="SET NULL"), index=True
    )
    purchased_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purchased_at: Mapped[date] = mapped_column(Date, nullable=False)
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", lazy="noload")
    catalog_part = relationship("PartsCatalog", lazy="noload")
    visit_charge = relationship("VisitCharge", lazy="noload")
    job = relationship("AgentAction", lazy="noload")
    property = relationship("Property", lazy="noload")
    water_feature = relationship("WaterFeature", lazy="noload")
    purchaser = relationship("User", lazy="noload")
