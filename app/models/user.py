"""
User database model.
Stores user authentication and profile information.
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class User(Base):
    """User model for authentication and user management."""

    __tablename__ = "users"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # Profile
    first_name = Column(String(100))
    last_name = Column(String(100))

    # Account status
    is_active = Column(Boolean, nullable=False, default=True)
    email_verified_at = Column(DateTime)
    email_verification_token = Column(String(100))
    password_reset_token = Column(String(100))
    password_reset_expires_at = Column(DateTime)

    # Login tracking
    last_login_at = Column(DateTime)
    last_login_ip = Column(String(45))
    login_count = Column(Integer, default=0)

    # Preferences
    timezone = Column(String(50))
    locale = Column(String(10), default='en_US')

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization_users = relationship(
        "OrganizationUser",
        foreign_keys="OrganizationUser.user_id",
        back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}')>"

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email
