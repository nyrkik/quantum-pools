"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import get_db
from src.core.config import settings
from src.core.exceptions import AuthenticationError, ValidationError
from src.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SetupAccountRequest,
    TokenResponse,
    UserResponse,
    OrgUserResponse,
    OrgBrandingResponse,
    MessageResponse,
)
from src.services.auth_service import AuthService
from src.api.deps import get_current_user, get_current_org_user, OrgUserContext, REFRESH_TOKEN_COOKIE
from src.models.user import User
from src.models.organization import Organization


def _branding(org) -> OrgBrandingResponse | None:
    if not org:
        return None
    return OrgBrandingResponse(
        logo_url=org.logo_url,
        primary_color=org.primary_color,
        tagline=org.tagline,
    )

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_access_token_expire_hours * 3600,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")


@router.post("/register", response_model=OrgUserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    try:
        user, org = await auth_service.register(
            email=body.email,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            organization_name=body.organization_name,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "registration_failed", "message": str(e)})

    _, access_token, refresh_token = await auth_service.login(email=body.email, password=body.password)
    _set_auth_cookies(response, access_token, refresh_token)

    return OrgUserResponse(
        user=UserResponse.model_validate(user),
        organization_id=org.id,
        organization_name=org.name,
        role="owner",
        is_developer=False,
        branding=_branding(org),
    )


@router.post("/login", response_model=OrgUserResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    try:
        user, access_token, refresh_token = await auth_service.login(
            email=body.email, password=body.password
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "login_failed", "message": str(e)},
        )

    _set_auth_cookies(response, access_token, refresh_token)

    # Get org context
    from src.models.organization_user import OrganizationUser
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.organization))
        .where(OrganizationUser.user_id == user.id, OrganizationUser.is_active == True)
        .limit(1)
    )
    org_user = result.unique().scalar_one_or_none()

    features: list[str] = []
    emd_tier = None
    if org_user:
        from src.services.feature_service import FeatureService
        feature_service = FeatureService(db)
        features = await feature_service.get_org_active_feature_slugs(org_user.organization_id)
        emd_tier = await feature_service.get_org_emd_tier(org_user.organization_id)

    return OrgUserResponse(
        user=UserResponse.model_validate(user),
        organization_id=org_user.organization_id if org_user else "",
        organization_name=org_user.organization.name if org_user and org_user.organization else "",
        role=org_user.role.value if org_user else "",
        is_developer=org_user.is_developer if org_user else False,
        features=features,
        emd_tier=emd_tier,
        branding=_branding(org_user.organization if org_user else None),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token_str = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": "no_refresh_token"})

    auth_service = AuthService(db)
    try:
        new_access, new_refresh = await auth_service.refresh_tokens(refresh_token_str)
    except AuthenticationError as e:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "refresh_failed", "message": str(e)},
        )

    _set_auth_cookies(response, new_access, new_refresh)
    return TokenResponse(
        access_token=new_access,
        expires_in=settings.jwt_access_token_expire_hours * 3600,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token_str = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token_str:
        auth_service = AuthService(db)
        await auth_service.logout(refresh_token_str)
    _clear_auth_cookies(response)
    return MessageResponse(message="Logged out successfully.")


@router.get("/me", response_model=OrgUserResponse)
async def get_me(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    features = await ctx.load_features(db)
    from src.services.feature_service import FeatureService
    feature_service = FeatureService(db)
    emd_tier = await feature_service.get_org_emd_tier(ctx.organization_id)
    # Load org for branding
    org_result = await db.execute(select(Organization).where(Organization.id == ctx.organization_id))
    org = org_result.scalar_one_or_none()
    return OrgUserResponse(
        user=UserResponse.model_validate(ctx.user),
        organization_id=ctx.organization_id,
        organization_name=ctx.organization_name,
        role=ctx.role.value,
        is_developer=ctx.org_user.is_developer,
        features=features,
        emd_tier=emd_tier,
        branding=_branding(org),
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Always return success to prevent email enumeration
    return MessageResponse(message="If an account exists with that email, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    # TODO: Implement password reset token verification
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Password reset not yet implemented.")


@router.post("/setup-account", response_model=MessageResponse)
async def setup_account(body: SetupAccountRequest, db: AsyncSession = Depends(get_db)):
    """Set up account for an invited user — set password and verify."""
    from src.core.security import get_password_hash

    result = await db.execute(
        select(User).where(
            User.email == body.email,
            User.verification_token == body.token,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired setup link.")

    user.hashed_password = get_password_hash(body.password)
    user.is_verified = True
    user.verification_token = None
    await db.commit()

    return MessageResponse(message="Account set up successfully. You can now log in.")
