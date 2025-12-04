"""
Issue model for tracking problems found during service visits.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.database import Base


class Issue(Base):
    """
    Represents an issue/problem found at a customer property.
    Can be linked to a visit or created independently.
    Managed separately for team review, assignment, and scheduling.
    """
    __tablename__ = "issues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.id"), nullable=True, index=True)  # Optional link to visit

    # Reporter
    reported_by_tech_id = Column(UUID(as_uuid=True), ForeignKey("techs.id"), nullable=False, index=True)
    reported_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Issue details
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="medium")  # low, medium, high, critical
    photos = Column(JSON, nullable=True)  # Array of photo URLs/paths

    # Status and assignment
    status = Column(String(20), default="pending")  # pending, scheduled, in_progress, resolved, closed
    assigned_tech_id = Column(UUID(as_uuid=True), ForeignKey("techs.id"), nullable=True, index=True)
    scheduled_date = Column(DateTime, nullable=True)

    # Resolution
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by_tech_id = Column(UUID(as_uuid=True), ForeignKey("techs.id"), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="issues")
    customer = relationship("Customer", back_populates="issues")
    visit = relationship("Visit", back_populates="issues")
    reported_by = relationship("Tech", foreign_keys=[reported_by_tech_id], back_populates="reported_issues")
    assigned_tech = relationship("Tech", foreign_keys=[assigned_tech_id], back_populates="assigned_issues")
    resolved_by = relationship("Tech", foreign_keys=[resolved_by_tech_id], back_populates="resolved_issues")
