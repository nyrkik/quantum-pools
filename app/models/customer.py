"""
Customer database model.
Stores customer information including address, service preferences, and constraints.
"""

from sqlalchemy import Column, String, Float, Integer, Time, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Customer(Base):
    """Customer model for pool service customers."""

    __tablename__ = "customers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Basic information
    name = Column(String(200), nullable=False, index=True)
    address = Column(String(500), nullable=False)

    # Geocoded location (populated by geocoding service)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Service configuration
    service_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="residential or commercial"
    )
    difficulty = Column(
        Integer,
        nullable=False,
        default=1,
        comment="1-5 difficulty scale affecting service duration"
    )

    # Scheduling
    service_day = Column(
        String(20),
        nullable=False,
        index=True,
        comment="monday, tuesday, wednesday, thursday, friday, saturday, sunday"
    )
    locked = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="If true, cannot be moved to a different service day during optimization"
    )

    # Time windows (optional - customer availability constraints)
    time_window_start = Column(
        Time,
        nullable=True,
        comment="Earliest time customer can be serviced"
    )
    time_window_end = Column(
        Time,
        nullable=True,
        comment="Latest time customer can be serviced"
    )

    # Metadata
    notes = Column(String(1000), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    route_stops = relationship(
        "RouteStop",
        back_populates="customer",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name='{self.name}', service_day='{self.service_day}')>"

    @property
    def base_service_duration(self) -> int:
        """
        Calculate base service duration in minutes based on type and difficulty.

        Returns:
            int: Service duration in minutes
        """
        # Base times
        if self.service_type == "commercial":
            base_time = 25
        else:  # residential
            base_time = 15

        # Adjust for difficulty (1=easy, 5=very hard)
        difficulty_adjustment = (self.difficulty - 1) * 5  # +5 min per difficulty level

        return base_time + difficulty_adjustment
