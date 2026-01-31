"""Route and RouteStop models for route optimization."""

import uuid
from datetime import datetime, timezone, time
from sqlalchemy import (
    String, DateTime, Float, Integer, ForeignKey, Time, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tech_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("techs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_day: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    total_duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    total_distance_miles: Mapped[float] = mapped_column(Float, default=0.0)
    total_stops: Mapped[int] = mapped_column(Integer, default=0)
    optimization_algorithm: Mapped[str | None] = mapped_column(String(50))
    optimization_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tech = relationship("Tech", lazy="noload")
    stops = relationship(
        "RouteStop",
        back_populates="route",
        cascade="all, delete-orphan",
        lazy="noload",
        order_by="RouteStop.sequence",
    )


class RouteStop(Base):
    __tablename__ = "route_stops"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    property_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_arrival_time: Mapped[time | None] = mapped_column(Time)
    estimated_service_duration: Mapped[int] = mapped_column(Integer, default=30)
    estimated_drive_time_from_previous: Mapped[int] = mapped_column(Integer, default=0)
    estimated_distance_from_previous: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    route = relationship("Route", back_populates="stops", lazy="noload")
    property = relationship("Property", lazy="noload")


class TempTechAssignment(Base):
    __tablename__ = "temp_tech_assignments"
    __table_args__ = (
        UniqueConstraint("organization_id", "property_id", name="uq_temp_assignment_org_property"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    property_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    temp_tech_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("techs.id", ondelete="CASCADE"),
        nullable=False,
    )
    temp_service_day: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
