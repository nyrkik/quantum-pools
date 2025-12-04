"""
Visit model for tracking tech service visits to customer properties.
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.database import Base


class Visit(Base):
    """
    Represents a service visit by a tech to a customer property.
    Auto-created from daily routes, completed by techs during/after service.
    """
    __tablename__ = "visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    tech_id = Column(UUID(as_uuid=True), ForeignKey("techs.id"), nullable=False, index=True)

    # Scheduling
    scheduled_date = Column(DateTime, nullable=False, index=True)  # When visit was scheduled
    service_day = Column(String(20), nullable=False)  # monday, tuesday, etc.

    # Actual timing (filled in by tech)
    actual_arrival_time = Column(DateTime, nullable=True)
    actual_departure_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)  # Calculated or manual

    # Service details
    service_performed = Column(Text, nullable=True)  # What work was done
    notes = Column(Text, nullable=True)  # General notes/comments
    photos = Column(JSON, nullable=True)  # Array of photo URLs/paths

    # Status tracking
    status = Column(String(20), default="scheduled")  # scheduled, in_progress, completed, cancelled, no_show

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)  # When status changed to completed

    # Relationships
    organization = relationship("Organization", back_populates="visits")
    customer = relationship("Customer", back_populates="visits")
    tech = relationship("Tech", back_populates="visits")
    issues = relationship("Issue", back_populates="visit", cascade="all, delete-orphan")
    services = relationship("VisitService", back_populates="visit", cascade="all, delete-orphan")
