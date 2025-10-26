"""
OrganizationUser database model.
Junction table for many-to-many relationship between users and organizations.
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class OrganizationUser(Base):
    """OrganizationUser model for user-organization membership and roles."""

    __tablename__ = "organization_users"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign keys
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Role and permissions
    role = Column(String(50), nullable=False, index=True)  # owner, admin, manager, technician, readonly
    is_primary_org = Column(Boolean, default=False)

    # Invitation tracking
    invitation_token = Column(String(100), index=True)
    invitation_accepted_at = Column(DateTime)
    invited_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraints
    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', name='uq_org_user'),
    )

    # Relationships
    organization = relationship("Organization", back_populates="organization_users")
    user = relationship("User", foreign_keys=[user_id], back_populates="organization_users")
    inviter = relationship("User", foreign_keys=[invited_by])

    def __repr__(self) -> str:
        return f"<OrganizationUser(user_id={self.user_id}, org_id={self.organization_id}, role='{self.role}')>"
