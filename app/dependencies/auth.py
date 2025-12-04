"""
Authentication dependencies for FastAPI endpoints.
Provides JWT token validation and user context extraction.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from app.database import get_db
from app.services.auth import AuthService
from app.models.user import User
from app.models.organization import Organization


# HTTP Bearer token scheme
security = HTTPBearer()


class AuthContext(BaseModel):
    """Authentication context extracted from JWT token."""

    user_id: UUID
    organization_id: UUID
    role: str
    email: str
    tech_id: Optional[UUID] = None
    user: Optional[User] = None
    organization: Optional[Organization] = None

    model_config = {"arbitrary_types_allowed": True}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> AuthContext:
    """
    Validate JWT token and return authentication context.

    Args:
        credentials: HTTP Bearer token from Authorization header
        db: Database session

    Returns:
        AuthContext with user_id, organization_id, role, and email

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    token = credentials.credentials

    # Decode and validate token
    payload = AuthService.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract claims from token
    try:
        user_id = UUID(payload.get("user_id"))
        organization_id = UUID(payload.get("organization_id"))
        role = payload.get("role")
        email = payload.get("email")
        tech_id = UUID(payload.get("tech_id")) if payload.get("tech_id") else None
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user exists and is active
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Verify organization exists and is active
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is disabled"
        )

    return AuthContext(
        user_id=user_id,
        organization_id=organization_id,
        role=role,
        email=email,
        tech_id=tech_id,
        user=user,
        organization=organization
    )


async def require_role(*allowed_roles: str):
    """
    Dependency factory to require specific roles.

    Usage:
        @router.get("/admin")
        async def admin_endpoint(
            auth: AuthContext = Depends(require_role("owner", "admin"))
        ):
            ...

    Args:
        allowed_roles: Roles that are allowed to access the endpoint

    Returns:
        Dependency function that validates role
    """
    async def role_checker(
        auth: AuthContext = Depends(get_current_user)
    ) -> AuthContext:
        if auth.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}"
            )
        return auth

    return role_checker


# Convenience dependencies for common role requirements
async def require_owner(
    auth: AuthContext = Depends(get_current_user)
) -> AuthContext:
    """Require 'owner' role."""
    if auth.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required"
        )
    return auth


async def require_admin(
    auth: AuthContext = Depends(get_current_user)
) -> AuthContext:
    """Require 'owner' or 'admin' role."""
    if auth.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return auth


async def require_manager(
    auth: AuthContext = Depends(get_current_user)
) -> AuthContext:
    """Require 'owner', 'admin', or 'manager' role."""
    if auth.role not in ("owner", "admin", "manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required"
        )
    return auth
