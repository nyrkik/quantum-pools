"""
Visit Service model - tracks services performed during a visit.
"""

import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class VisitService(Base):
    """Services performed during a visit."""
    __tablename__ = "visit_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False)
    service_catalog_id = Column(UUID(as_uuid=True), ForeignKey("service_catalog.id"), nullable=True)

    # Custom service (if not from catalog)
    custom_service_name = Column(String(200))

    # Additional details
    notes = Column(Text)
    completed_at = Column(DateTime, default=datetime.utcnow)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    visit = relationship("Visit", back_populates="services")
    service = relationship("ServiceCatalog", back_populates="visit_services")
