"""
Tech (Technician) database model.
Stores technician information including start/end locations and working hours.
"""

from sqlalchemy import Column, String, Float, Integer, Time, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Tech(Base):
    """Tech/Technician model for route planning."""

    __tablename__ = "techs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Multi-tenancy
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id'),
        nullable=False,
        index=True,
        comment="Organization this tech belongs to"
    )

    # Basic information
    name = Column(String(200), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    color = Column(
        String(7),
        nullable=False,
        default='#3498db',
        comment="Hex color code for route visualization"
    )

    # Geocoding metadata
    geocoding_provider = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Provider used for geocoding (google, mapbox, etc.)"
    )
    geocoded_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When geocoding was last performed"
    )

    # Start location (where tech begins their route)
    start_location_address = Column(String(500), nullable=False)
    start_latitude = Column(Float, nullable=True)
    start_longitude = Column(Float, nullable=True)

    # End location (where tech ends their route - can be same as start)
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
        comment="Maximum number of customers this tech can service in one day"
    )
    efficiency_multiplier = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="Efficiency multiplier for route optimization (e.g., 1.5 = 50% more efficient)"
    )

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this tech is currently active/available"
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
    organization = relationship("Organization", back_populates="techs")
    routes = relationship(
        "Route",
        back_populates="tech",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tech(id={self.id}, name='{self.name}', is_active={self.is_active})>"

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
