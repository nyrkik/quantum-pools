"""Tech (technician) model — operational profile for field workers."""

import uuid
from datetime import datetime, date, timezone, time
from sqlalchemy import String, Boolean, Date, DateTime, Float, Integer, Text, ForeignKey, JSON, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Tech(Base):
    __tablename__ = "techs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    color: Mapped[str] = mapped_column(String(7), default="#3B82F6")

    # Home/start location
    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lng: Mapped[float | None] = mapped_column(Float)
    start_address: Mapped[str | None] = mapped_column(String(255))
    end_lat: Mapped[float | None] = mapped_column(Float)
    end_lng: Mapped[float | None] = mapped_column(Float)
    end_address: Mapped[str | None] = mapped_column(String(255))

    # Schedule
    work_start_time: Mapped[time | None] = mapped_column(Time)
    work_end_time: Mapped[time | None] = mapped_column(Time)
    working_days: Mapped[dict | None] = mapped_column(JSON)
    max_stops_per_day: Mapped[int] = mapped_column(Integer, default=20)
    efficiency_factor: Mapped[float] = mapped_column(Float, default=1.0)

    # Link to user account (optional — not all techs have app logins)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)

    # Compensation
    hourly_rate: Mapped[float | None] = mapped_column(Float)
    overtime_rate: Mapped[float | None] = mapped_column(Float)

    # Capabilities — JSON for flexibility, easy to query with PostgreSQL
    skills: Mapped[dict | None] = mapped_column(JSON)           # ["equipment_repair", "weekly_service", "heater_repair"]
    certifications: Mapped[dict | None] = mapped_column(JSON)   # [{"name": "CPO", "number": "12345", "expires": "2027-06-15"}]
    service_types: Mapped[dict | None] = mapped_column(JSON)    # ["weekly_maintenance", "repair", "equipment_install"]

    # Territory
    territory_zone: Mapped[str | None] = mapped_column(String(50))  # "north", "east_sac", "folsom"

    # Vehicle
    vehicle_type: Mapped[str | None] = mapped_column(String(50))    # truck, van, suv
    vehicle_plate: Mapped[str | None] = mapped_column(String(20))

    # Admin
    job_title: Mapped[str | None] = mapped_column(String(100))      # "Senior Technician", "Office Manager"
    hire_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)                 # Freeform context for AI: "Best with commercial accounts"

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    visits = relationship("Visit", back_populates="tech", lazy="noload")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
