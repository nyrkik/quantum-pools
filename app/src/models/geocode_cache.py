"""GeocodeCache model — cached geocoding results."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    address_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
