"""Scraper run log — tracks EMD scraper execution history."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, success, error
    days_scraped: Mapped[int] = mapped_column(Integer, default=0)
    inspections_found: Mapped[int] = mapped_column(Integer, default=0)
    inspections_new: Mapped[int] = mapped_column(Integer, default=0)
    pdfs_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
