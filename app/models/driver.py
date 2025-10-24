"""
Driver database model.
Stores driver/technician information including start/end locations and working hours.
"""

from sqlalchemy import Column, String, Float, Integer, Time, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Driver(Base):
    """Driver/Technician model for route planning."""

    __tablename__ = "drivers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Basic information
    name = Column(String(200), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)

    # Start location (where driver begins their route)
    start_location_address = Column(String(500), nullable=False)
    start_latitude = Column(Float, nullable=True)
    start_longitude = Column(Float, nullable=True)

    # End location (where driver ends their route - can be same as start)
    end_location_address = Column(String(500), nullable=False)
    end_latitude = Column(Float, nullable=True)
    end_longitude = Column(Float, nullable=True)

    # Working hours
    working_hours_start = Column(
        Time,
        nullable=False,
        default=datetime.strptime("08:00", "%H:%M").time(),
        comment="Start of workday"
    )
    working_hours_end = Column(
        Time,
        nullable=False,
        default=datetime.strptime("17:00", "%H:%M").time(),
        comment="End of workday"
    )

    # Configuration
    max_customers_per_day = Column(
        Integer,
        nullable=False,
        default=20,
        comment="Maximum number of customers this driver can service in one day"
    )

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this driver is currently active/available"
    )

    # Metadata
    notes = Column(String(1000), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    routes = relationship(
        "Route",
        back_populates="driver",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Driver(id={self.id}, name='{self.name}', is_active={self.is_active})>"

    @property
    def working_hours_duration(self) -> int:
        """
        Calculate total working hours in minutes.

        Returns:
            int: Working hours in minutes
        """
        start_minutes = self.working_hours_start.hour * 60 + self.working_hours_start.minute
        end_minutes = self.working_hours_end.hour * 60 + self.working_hours_end.minute
        return end_minutes - start_minutes
