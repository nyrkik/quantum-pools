"""
Authentication service for password hashing and JWT token generation.
"""

import bcrypt
import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.organization_user import OrganizationUser
from app.models.organization import Organization


# JWT Configuration
JWT_SECRET_KEY = "CHANGE_ME_IN_PRODUCTION_USE_ENV_VARIABLE"  # TODO: Move to environment variable
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            str: Hashed password
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            password: Plain text password
            hashed_password: Hashed password to verify against

        Returns:
            bool: True if password matches, False otherwise
        """
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

    @staticmethod
    def generate_token(user_id: UUID, organization_id: UUID, role: str, email: str, tech_id: Optional[UUID] = None) -> str:
        """
        Generate a JWT access token.

        Args:
            user_id: User's UUID
            organization_id: Organization's UUID
            role: User's role in the organization
            email: User's email address
            tech_id: Optional Tech UUID if user is linked to a tech

        Returns:
            str: JWT token
        """
        expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)

        payload = {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "role": role,
            "email": email,
            "exp": expiration,
            "iat": datetime.utcnow(),
        }

        if tech_id:
            payload["tech_id"] = str(tech_id)

        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return token

    @staticmethod
    def decode_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Decode and verify a JWT token.

        Args:
            token: JWT token to decode

        Returns:
            Optional[Dict]: Token payload if valid, None if invalid or expired
        """
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def generate_reset_token() -> str:
        """
        Generate a secure random token for password resets.

        Returns:
            str: Random token
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """
        Get user by email address.

        Args:
            db: Database session
            email: Email address (case-insensitive)

        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_primary_organization(db: AsyncSession, user_id: UUID) -> Optional[tuple[Organization, str]]:
        """
        Get user's primary organization and role.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Optional[tuple]: (Organization, role) if found, None otherwise
        """
        result = await db.execute(
            select(Organization, OrganizationUser.role)
            .join(OrganizationUser, Organization.id == OrganizationUser.organization_id)
            .where(
                OrganizationUser.user_id == user_id,
                OrganizationUser.is_primary_org == True
            )
        )
        row = result.first()
        return (row[0], row[1]) if row else None

    @staticmethod
    async def update_last_login(db: AsyncSession, user_id: UUID, ip_address: Optional[str] = None) -> None:
        """
        Update user's last login timestamp and IP address.

        Args:
            db: Database session
            user_id: User's UUID
            ip_address: Optional IP address of login
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.last_login_at = datetime.utcnow()
            user.login_count = (user.login_count or 0) + 1
            if ip_address:
                user.last_login_ip = ip_address

            await db.commit()
