"""
Temporary Tech Assignment Model
Stores temporary (day-only) tech assignments for customers
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid

from app.database import Base


class TempTechAssignment(Base):
    """
    Temporary tech assignment for a specific customer on a specific day.
    Used when reassigning techs temporarily without updating the permanent customer record.
    """
    __tablename__ = "temp_tech_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=False)
    tech_id = Column(UUID(as_uuid=True), ForeignKey('techs.id'), nullable=False)
    service_day = Column(String(20), nullable=False)  # monday, tuesday, etc.
    assignment_date = Column(Date, nullable=False, default=date.today)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    customer = relationship("Customer")
    tech = relationship("Tech")

    # Index for fast lookups
    __table_args__ = (
        Index('ix_temp_assignments_customer_day', 'customer_id', 'service_day', 'assignment_date'),
        Index('ix_temp_assignments_org_date', 'organization_id', 'assignment_date'),
    )
