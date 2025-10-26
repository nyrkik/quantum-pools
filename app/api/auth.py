"""
Authentication API endpoints.
Handles user registration, login, and token management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import uuid
import re

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.organization_user import OrganizationUser
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserInfo,
    OrganizationInfo,
)
from app.services.auth import AuthService


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def slugify(text: str) -> str:
    """
    Convert text to URL-friendly slug.

    Args:
        text: Text to convert

    Returns:
        str: Slugified text
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user and organization.

    Creates:
    - New user account
    - New organization (user becomes owner)
    - Organization-user relationship

    Returns JWT token for immediate authentication.
    """
    # Check if user already exists
    existing_user = await AuthService.get_user_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Generate organization slug
    base_slug = slugify(request.organization_name)
    slug = base_slug
    counter = 1

    # Ensure unique slug
    while True:
        result = await db.execute(
            select(Organization).where(Organization.slug == slug)
        )
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Create organization
    organization = Organization(
        id=uuid.uuid4(),
        name=request.organization_name,
        slug=slug,
        plan_tier='starter',
        subscription_status='trial',
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
        trial_days=14,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(organization)

    # Create user
    user = User(
        id=uuid.uuid4(),
        email=request.email.lower(),
        password_hash=AuthService.hash_password(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        is_active=True,
        email_verified_at=datetime.utcnow(),  # Auto-verify for now
        login_count=0,
        locale='en_US',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)

    # Create organization-user relationship
    org_user = OrganizationUser(
        id=uuid.uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        role='owner',
        is_primary_org=True,
        invitation_accepted_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(org_user)

    await db.commit()
    await db.refresh(user)
    await db.refresh(organization)

    # Update last login
    client_ip = req.client.host if req.client else None
    await AuthService.update_last_login(db, user.id, client_ip)

    # Generate JWT token
    token = AuthService.generate_token(
        user_id=user.id,
        organization_id=organization.id,
        role='owner',
        email=user.email
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=24 * 3600,  # 24 hours in seconds
        user=UserInfo(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            email_verified_at=user.email_verified_at,
        ),
        organization=OrganizationInfo(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role='owner',
        )
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT token.

    Validates credentials and returns token for user's primary organization.
    """
    # Get user by email
    user = await AuthService.get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    if not AuthService.verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )

    # Get user's primary organization
    org_info = await AuthService.get_user_primary_organization(db, user.id)
    if not org_info:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User has no organization"
        )

    organization, role = org_info

    # Update last login
    client_ip = req.client.host if req.client else None
    await AuthService.update_last_login(db, user.id, client_ip)

    # Generate JWT token
    token = AuthService.generate_token(
        user_id=user.id,
        organization_id=organization.id,
        role=role,
        email=user.email
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=24 * 3600,  # 24 hours in seconds
        user=UserInfo(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            email_verified_at=user.email_verified_at,
        ),
        organization=OrganizationInfo(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role=role,
        )
    )
