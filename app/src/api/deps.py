"""FastAPI dependencies for auth, RBAC, and org-scoping."""

from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import get_db
from src.core.security import decode_token, verify_token_type
from src.core.exceptions import AuthenticationError
from src.models.user import User
from src.models.organization_user import OrganizationUser, OrgRole

import logging

logger = logging.getLogger(__name__)

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"


class CustomHTTPBearer(HTTPBearer):
    """HTTPBearer with cookie fallback for HttpOnly token storage."""

    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        try:
            result = await super().__call__(request)
            if result:
                return result
        except HTTPException:
            pass

        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required", "message": "Authentication token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )


security = CustomHTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        token = credentials.credentials
        payload = decode_token(token)
        verify_token_type(payload, "access")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing user ID")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AuthenticationError("User not found")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "account_inactive"})
        return user
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": str(e)},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected auth error: {e}")
        raise HTTPException(status_code=500, detail={"error": "authentication_error"})


async def get_current_user_optional(
    request: Request, db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    try:
        token = None
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        if not token:
            token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if not token:
            return None
        payload = decode_token(token)
        verify_token_type(payload, "access")
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user if user and user.is_active else None
    except Exception:
        return None


class OrgUserContext:
    """Contains the authenticated user and their org membership."""
    def __init__(self, user: User, org_user: OrganizationUser, org_name: str):
        self.user = user
        self.org_user = org_user
        self.organization_id = org_user.organization_id
        self.organization_name = org_name
        self.role = org_user.role


async def get_current_org_user(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgUserContext:
    """Get current user with their org context."""
    org_id = request.headers.get("X-Organization-Id")

    if org_id:
        result = await db.execute(
            select(OrganizationUser)
            .options(joinedload(OrganizationUser.organization))
            .where(
                OrganizationUser.user_id == user.id,
                OrganizationUser.organization_id == org_id,
                OrganizationUser.is_active == True,
            )
        )
        org_user = result.unique().scalar_one_or_none()
    else:
        result = await db.execute(
            select(OrganizationUser)
            .options(joinedload(OrganizationUser.organization))
            .where(OrganizationUser.user_id == user.id, OrganizationUser.is_active == True)
            .limit(1)
        )
        org_user = result.unique().scalar_one_or_none()

    if not org_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "no_organization", "message": "You are not a member of any organization."},
        )

    org_name = org_user.organization.name if org_user.organization else ""
    return OrgUserContext(user=user, org_user=org_user, org_name=org_name)


def require_roles(*roles: OrgRole):
    """Dependency factory: require one of the specified roles."""
    async def _check_role(ctx: OrgUserContext = Depends(get_current_org_user)):
        if ctx.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "insufficient_permissions", "message": f"Requires: {', '.join(r.value for r in roles)}"},
            )
        return ctx
    return _check_role
