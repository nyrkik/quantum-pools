"""
Tech Route Model
Stores persistent routes for each tech on each service day
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Date, Float, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid

from app.database import Base


class TechRoute(Base):
    """
    Persistent route for a tech on a specific service day.
    Contains the optimized stop sequence for that tech's customers.
    """
    __tablename__ = "tech_routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    tech_id = Column(UUID(as_uuid=True), ForeignKey('techs.id'), nullable=False)
    service_day = Column(String(20), nullable=False)  # monday, tuesday, etc.
    route_date = Column(Date, nullable=False, default=date.today)
    stop_sequence = Column(JSONB, nullable=False)  # Array of customer IDs in order
    total_distance = Column(Float, nullable=True)  # Miles
    total_duration = Column(Integer, nullable=True)  # Minutes
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    tech = relationship("Tech")

    # Indexes
    __table_args__ = (
        Index('ix_tech_routes_org_date', 'organization_id', 'route_date'),
        Index('ix_tech_routes_tech_day_date', 'tech_id', 'service_day', 'route_date', unique=True),
    )
