"""
Route and RouteStop database models.
Represents optimized routes assigned to techs (technicians).
"""

from sqlalchemy import Column, String, Integer, Float, Time, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Route(Base):
    """Route model representing a tech's route for a specific day."""

    __tablename__ = "routes"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Multi-tenancy
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id'),
        nullable=False,
        index=True,
        comment="Organization this route belongs to"
    )

    # Foreign keys
    tech_id = Column(
        UUID(as_uuid=True),
        ForeignKey("techs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Route details
    service_day = Column(
        String(20),
        nullable=False,
        index=True,
        comment="monday, tuesday, wednesday, thursday, friday, saturday, sunday"
    )

    # Metrics (calculated during optimization)
    total_duration_minutes = Column(
        Integer,
        nullable=True,
        comment="Total route duration including driving and service time"
    )
    total_distance_miles = Column(
        Float,
        nullable=True,
        comment="Total driving distance in miles"
    )
    total_customers = Column(
        Integer,
        nullable=True,
        comment="Total number of customers on this route"
    )

    # Optimization metadata
    optimization_algorithm = Column(
        String(100),
        nullable=True,
        default="google-or-tools",
        comment="Algorithm used to generate this route"
    )
    optimization_score = Column(
        Float,
        nullable=True,
        comment="Quality score of the optimization (if available)"
    )

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    organization = relationship("Organization", back_populates="routes")
    tech = relationship("Tech", back_populates="routes")
    stops = relationship(
        "RouteStop",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteStop.sequence"
    )

    def __repr__(self) -> str:
        return (
            f"<Route(id={self.id}, tech_id={self.tech_id}, "
            f"service_day='{self.service_day}', customers={self.total_customers})>"
        )


class RouteStop(Base):
    """RouteStop model representing individual customer stops within a route."""

    __tablename__ = "route_stops"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign keys
    route_id = Column(
        UUID(as_uuid=True),
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Stop details
    sequence = Column(
        Integer,
        nullable=False,
        comment="Order of this stop in the route (1-based)"
    )

    # Timing estimates
    estimated_arrival_time = Column(
        Time,
        nullable=True,
        comment="Estimated time of arrival at this customer"
    )
    estimated_service_duration = Column(
        Integer,
        nullable=True,
        comment="Estimated service time in minutes"
    )
    estimated_drive_time_from_previous = Column(
        Integer,
        nullable=True,
        comment="Estimated driving time from previous stop in minutes"
    )
    estimated_distance_from_previous = Column(
        Float,
        nullable=True,
        comment="Distance from previous stop in miles"
    )

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    route = relationship("Route", back_populates="stops")
    customer = relationship("Customer", back_populates="route_stops")

    def __repr__(self) -> str:
        return (
            f"<RouteStop(id={self.id}, route_id={self.route_id}, "
            f"customer_id={self.customer_id}, sequence={self.sequence})>"
        )
