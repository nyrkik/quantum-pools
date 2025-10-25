"""
Customer database model.
Stores customer information including address, service preferences, and constraints.
"""

from sqlalchemy import Column, String, Float, Integer, Time, DateTime, Boolean, ForeignKey
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
    name = Column(String(200), nullable=True, comment="Business name (for commercial) or full name (legacy)")
    first_name = Column(String(100), nullable=True, comment="First name (for residential)")
    last_name = Column(String(100), nullable=True, comment="Last name (for residential)")
    display_name = Column(String(200), nullable=False, index=True, comment="Display name (auto-generated if not provided)")
    address = Column(String(500), nullable=False)

    # Contact information
    email = Column(String(255), nullable=True, comment="Primary email address")
    phone = Column(String(20), nullable=True, comment="Primary phone number")
    alt_email = Column(String(255), nullable=True, comment="Alternate email address")
    alt_phone = Column(String(20), nullable=True, comment="Alternate phone number")
    invoice_email = Column(String(255), nullable=True, comment="Invoice email (for commercial)")

    # Management company (for commercial properties)
    management_company = Column(String(200), nullable=True, comment="Management company name (for commercial)")

    # Geocoded location (populated by geocoding service)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Assigned driver/technician
    assigned_driver_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drivers.id'),
        nullable=True,
        comment="Driver assigned to service this customer"
    )

    # Service configuration
    service_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="residential or commercial"
    )
    visit_duration = Column(
        Integer,
        nullable=False,
        default=15,
        comment="Visit duration in minutes"
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
        comment="Primary service day: monday, tuesday, wednesday, thursday, friday, saturday, sunday"
    )
    service_days_per_week = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of service days per week (1, 2, or 3)"
    )
    service_schedule = Column(
        String(50),
        nullable=True,
        comment="Current schedule pattern (e.g., 'Mo/Th', 'Mo/We/Fr'). NULL for single-day schedules."
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
    assigned_driver = relationship(
        "Driver",
        foreign_keys=[assigned_driver_id]
    )
    route_stops = relationship(
        "RouteStop",
        back_populates="customer",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, display_name='{self.display_name}', service_day='{self.service_day}')>"

    @property
    def base_service_duration(self) -> int:
        """
        Calculate service duration in minutes based on visit_duration and difficulty.

        Returns:
            int: Service duration in minutes
        """
        # Use the visit_duration field as base time
        base_time = self.visit_duration

        # Adjust for difficulty (1=easy, 5=very hard)
        difficulty_adjustment = (self.difficulty - 1) * 5  # +5 min per difficulty level

        return base_time + difficulty_adjustment
