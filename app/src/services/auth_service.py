"""Authentication service — register, login, token management."""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from src.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token_type,
)
from src.core.exceptions import AuthenticationError, ValidationError
from src.models.user import User
from src.models.organization import Organization
from src.models.organization_user import OrganizationUser, OrgRole
from src.models.user_session import UserSession

logger = logging.getLogger(__name__)

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self, email: str, password: str, first_name: str, last_name: str, organization_name: str
    ) -> Tuple[User, Organization]:
        """Register a new user and create their organization."""
        existing = await self.db.execute(select(User).where(func.lower(User.email) == email.lower()))
        if existing.scalar_one_or_none():
            raise ValidationError("An account with this email already exists.")

        user = User(
            id=str(uuid.uuid4()),
            email=email.lower().strip(),
            hashed_password=get_password_hash(password),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)

        org = Organization(
            id=str(uuid.uuid4()),
            name=organization_name.strip(),
            slug=self._slugify(organization_name),
            is_active=True,
        )
        self.db.add(org)

        org_user = OrganizationUser(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=OrgRole.owner,
            is_active=True,
        )
        self.db.add(org_user)

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(org)
        return user, org

    async def login(self, email: str, password: str) -> Tuple[User, str, str]:
        """Authenticate user, return (user, access_token, refresh_token)."""
        result = await self.db.execute(select(User).where(func.lower(User.email) == email.lower()))
        user = result.scalar_one_or_none()

        if not user:
            raise AuthenticationError("Invalid email or password.")

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
            raise AuthenticationError(f"Account locked. Try again in {remaining} minutes.")

        if not verify_password(password, user.hashed_password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                logger.warning(f"Account locked for user {user.email}")
            await self.db.commit()
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationError("Account is inactive.")

        # Reset failed attempts on successful login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now(timezone.utc)

        access_token = create_access_token(data={"sub": user.id})
        refresh_token, jti, expire = create_refresh_token(data={"sub": user.id})

        # Store session
        session = UserSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            jti=jti,
            expires_at=expire,
        )
        self.db.add(session)
        await self.db.commit()

        return user, access_token, refresh_token

    async def refresh_tokens(self, refresh_token_str: str) -> Tuple[str, str]:
        """Rotate refresh token, return new (access_token, refresh_token)."""
        try:
            payload = decode_token(refresh_token_str)
            verify_token_type(payload, "refresh")
        except Exception as e:
            raise AuthenticationError(f"Invalid refresh token: {e}")

        user_id = payload.get("sub")
        jti = payload.get("jti")
        if not user_id or not jti:
            raise AuthenticationError("Invalid refresh token payload.")

        result = await self.db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.jti == jti,
                UserSession.is_revoked == False,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise AuthenticationError("Session not found or already revoked.")

        if session.expires_at < datetime.now(timezone.utc):
            session.is_revoked = True
            await self.db.commit()
            raise AuthenticationError("Refresh token expired.")

        # Revoke old session
        session.is_revoked = True

        # Issue new tokens
        new_access = create_access_token(data={"sub": user_id})
        new_refresh, new_jti, new_expire = create_refresh_token(data={"sub": user_id})

        new_session = UserSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            jti=new_jti,
            expires_at=new_expire,
        )
        self.db.add(new_session)
        await self.db.commit()

        return new_access, new_refresh

    async def logout(self, refresh_token_str: str) -> None:
        """Revoke the refresh token session."""
        try:
            payload = decode_token(refresh_token_str)
            jti = payload.get("jti")
            if jti:
                result = await self.db.execute(
                    select(UserSession).where(UserSession.jti == jti)
                )
                session = result.scalar_one_or_none()
                if session:
                    session.is_revoked = True
                    await self.db.commit()
        except Exception:
            pass  # Best-effort logout

    @staticmethod
    def _slugify(name: str) -> str:
        import re
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")
