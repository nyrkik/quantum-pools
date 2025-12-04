"""
Service Catalog model - standardized list of services.
"""

import uuid
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class ServiceCatalog(Base):
    """Catalog of standardized services for pool maintenance."""
    __tablename__ = "service_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    # Service details
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(100))  # e.g., "Cleaning", "Chemical", "Repair", "Inspection"
    estimated_duration = Column(Integer)  # Minutes

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="service_catalog")
    visit_services = relationship("VisitService", back_populates="service")
