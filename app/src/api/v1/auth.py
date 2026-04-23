"""Authentication endpoints."""

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import joinedload

from src.core.database import get_db
from src.core.config import settings
from src.core.exceptions import AuthenticationError, ValidationError
from src.core.rate_limiter import limiter
from pydantic import BaseModel, Field
from typing import Optional
from src.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    RecoverEmailRequest,
    RecoverEmailResponse,
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
from src.models.organization_user import OrganizationUser
from src.models.user_session import UserSession

logger = logging.getLogger(__name__)

RESET_TOKEN_TTL_HOURS = 1


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_phone(raw: str) -> str:
    """Strip everything except digits. Leading +/country code collapses to digits too."""
    return re.sub(r"\D+", "", raw or "")


def _mask_email(email: str) -> str:
    """b****@g***.com — show first char + TLD suffix, mask the rest."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    if "." in domain:
        dom_name, _, tld = domain.rpartition(".")
        masked_domain = (dom_name[0] if dom_name else "") + "*" * max(len(dom_name) - 1, 3) + "." + tld
    else:
        masked_domain = (domain[0] if domain else "") + "*" * max(len(domain) - 1, 3)
    masked_local = (local[0] if local else "") + "*" * max(len(local) - 1, 3)
    return f"{masked_local}@{masked_domain}"


def _branding(org) -> OrgBrandingResponse | None:
    if not org:
        return None
    return OrgBrandingResponse(
        logo_url=org.logo_url,
        primary_color=org.primary_color,
        tagline=org.tagline,
    )

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str, request: Request | None = None) -> None:
    # Detect if request came via the tunnel domain (HTTPS) or local/Tailscale (HTTP)
    is_tunnel = False
    if request:
        origin = request.headers.get("origin", "")
        host = request.headers.get("host", "")
        is_tunnel = "quantumpoolspro.com" in origin or "quantumpoolspro.com" in host

    if is_tunnel:
        # Tunnel: cross-subdomain cookies with Secure + SameSite=None
        is_secure = True
        domain = settings.cookie_domain  # ".quantumpoolspro.com"
        samesite = "none"
    else:
        # Local/Tailscale: no domain restriction, no Secure flag
        is_secure = False
        domain = None
        samesite = "lax"

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        max_age=settings.jwt_access_token_expire_hours * 3600,
        path="/",
        domain=domain,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/v1/auth",
        domain=domain,
    )


def _clear_auth_cookies(response: Response, request: Request | None = None) -> None:
    # Clear both tunnel-domain and local cookies to cover all access paths
    domain = settings.cookie_domain
    response.delete_cookie(key="access_token", path="/", domain=domain)
    response.delete_cookie(key="refresh_token", path="/api/v1/auth", domain=domain)
    # Also clear without domain (covers local/Tailscale access)
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")


@router.post("/register", response_model=OrgUserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
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
    _set_auth_cookies(response, access_token, refresh_token, request)

    # Resolve permissions for the new owner
    from src.models.organization_user import OrganizationUser
    ou_result = await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.user_id == user.id,
            OrganizationUser.organization_id == org.id,
        )
    )
    org_user = ou_result.scalar_one_or_none()
    permissions: dict[str, str] = {}
    if org_user:
        from src.services.permission_service import PermissionService
        permissions = await PermissionService(db).resolve_permissions(org_user)

    return OrgUserResponse(
        user=UserResponse.model_validate(user),
        organization_id=org.id,
        organization_name=org.name,
        role="owner",
        is_developer=False,
        branding=_branding(org),
        permissions=permissions,
    )


@router.post("/login", response_model=OrgUserResponse)
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
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

    _set_auth_cookies(response, access_token, refresh_token, request)

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
    inspection_tier = None
    permissions: dict[str, str] = {}
    if org_user:
        from src.services.feature_service import FeatureService
        feature_service = FeatureService(db)
        features = await feature_service.get_org_active_feature_slugs(org_user.organization_id)
        inspection_tier = await feature_service.get_org_inspection_tier(org_user.organization_id)
        from src.services.permission_service import PermissionService
        perm_service = PermissionService(db)
        permissions = await perm_service.resolve_permissions(org_user)

    return OrgUserResponse(
        user=UserResponse.model_validate(user),
        organization_id=org_user.organization_id if org_user else "",
        organization_name=org_user.organization.name if org_user and org_user.organization else "",
        role=org_user.role.value if org_user else "",
        is_developer=org_user.is_developer if org_user else False,
        features=features,
        inspection_tier=inspection_tier,
        branding=_branding(org_user.organization if org_user else None),
        role_version=org_user.role_version if org_user else 0,
        permissions=permissions,
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

    _set_auth_cookies(response, new_access, new_refresh, request)
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
    permissions = await ctx.load_permissions(db)
    from src.services.feature_service import FeatureService
    feature_service = FeatureService(db)
    inspection_tier = await feature_service.get_org_inspection_tier(ctx.organization_id)
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
        inspection_tier=inspection_tier,
        branding=_branding(org),
        role_version=ctx.org_user.role_version or 0,
        permissions=permissions,
        inbox_v2_enabled=bool(getattr(org, "inbox_v2_enabled", False)) if org else False,
    )


@router.get("/me/email-signature")
async def get_my_email_signature(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's per-org email signature + the org-level
    composition toggles that affect how it renders in outbound mail. The
    frontend uses these together to render the live preview."""
    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one_or_none()
    return {
        "email_signature": ctx.org_user.email_signature,
        "email_signoff": ctx.org_user.email_signoff,
        # Mirrored from the org for preview convenience — read-only here;
        # admin edits via /v1/branding.
        "org_auto_signature_prefix": bool(getattr(org, "auto_signature_prefix", True)) if org else True,
        "org_include_logo_in_signature": bool(getattr(org, "include_logo_in_signature", False)) if org else False,
        "org_allow_per_user_signature": bool(getattr(org, "allow_per_user_signature", True)) if org else True,
        "org_signature_fallback": getattr(org, "agent_signature", None) if org else None,
        "org_name": org.name if org else None,
        "org_logo_url": getattr(org, "logo_url", None) if org else None,
    }


class MyEmailSignatureUpdate(BaseModel):
    email_signature: Optional[str] = None
    email_signoff: Optional[str] = None


class SignaturePreviewBody(BaseModel):
    """Payload for an uncommitted-preview render. Each field is optional —
    omitted fields fall back to the caller's saved state. Lets the UI
    preview changes without saving first."""
    user_signature: Optional[str] = None
    user_signoff: Optional[str] = None
    auto_signature_prefix: Optional[bool] = None
    include_logo_in_signature: Optional[bool] = None
    allow_per_user_signature: Optional[bool] = None
    website_url: Optional[str] = None
    org_signature: Optional[str] = None
    # If true, preview uses the caller's first_name + org_name for the
    # prefix block. Callers set this from the current user session.
    use_current_user: bool = True


@router.post("/me/email-signature/preview")
async def preview_my_email_signature(
    body: SignaturePreviewBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Server-side signature preview so the frontend doesn't have to
    reimplement the autolinker / prefix logic. Returns plain + html blocks
    identical to what send_agent_reply produces, minus the logo CID
    (previews don't need to round-trip the image)."""
    from src.services.email_signature import compose_signature

    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one_or_none()

    auto_prefix = (
        body.auto_signature_prefix
        if body.auto_signature_prefix is not None
        else bool(getattr(org, "auto_signature_prefix", True)) if org else True
    )
    include_logo = (
        body.include_logo_in_signature
        if body.include_logo_in_signature is not None
        else bool(getattr(org, "include_logo_in_signature", False)) if org else False
    )
    org_sig = (
        body.org_signature
        if body.org_signature is not None
        else (getattr(org, "agent_signature", None) if org else None)
    )
    allow_per_user = (
        body.allow_per_user_signature
        if body.allow_per_user_signature is not None
        else bool(getattr(org, "allow_per_user_signature", True)) if org else True
    )
    if allow_per_user:
        user_sig = (
            body.user_signature
            if body.user_signature is not None
            else ctx.org_user.email_signature
        )
        user_signoff = (
            body.user_signoff
            if body.user_signoff is not None
            else ctx.org_user.email_signoff
        )
    else:
        user_sig = None
        user_signoff = None

    effective_website = (
        body.website_url
        if body.website_url is not None
        else (getattr(org, "website_url", None) if org else None)
    )

    sig = compose_signature(
        sender_first_name=ctx.user.first_name if body.use_current_user else None,
        org_name=(org.name if org else None),
        auto_signature_prefix=auto_prefix,
        user_signature=user_sig,
        org_signature=org_sig,
        include_logo=include_logo,
        logo_url=(org.logo_url if org else None),
        # Preview: pass no logo bytes — the UI renders the logo_url directly
        # via <img src>. The cid-attachment path only runs at actual send.
        logo_bytes=None,
        user_signoff=user_signoff,
        website_url=effective_website,
    )
    return {
        "plain": sig.plain,
        "html": sig.html,
        "logo_url": org.logo_url if org and include_logo else None,
        "website_url": effective_website,
        "org_name": org.name if org else None,
        "sender_first_name": ctx.user.first_name,
    }


@router.put("/me/email-signature")
async def update_my_email_signature(
    body: MyEmailSignatureUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's per-org email signature + sign-off.
    Omitted fields are left alone; explicit empty string / null clears.
    Cleared signature falls back to Organization.agent_signature."""
    if body.email_signature is not None:
        text = body.email_signature.strip()
        ctx.org_user.email_signature = text or None
    if body.email_signoff is not None:
        signoff = body.email_signoff.strip()
        ctx.org_user.email_signoff = signoff or None
    await db.commit()
    return {
        "email_signature": ctx.org_user.email_signature,
        "email_signoff": ctx.org_user.email_signoff,
    }


@router.get("/my-orgs")
async def list_my_orgs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all organizations the current user belongs to (for dev org switching)."""
    from src.models.organization_user import OrganizationUser
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.organization))
        .where(OrganizationUser.user_id == user.id, OrganizationUser.is_active == True)
    )
    return [
        {"id": ou.organization_id, "name": ou.organization.name}
        for ou in result.unique().scalars().all()
    ]


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/hour")
async def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Issue a password-reset token and email it to the user.

    Always returns the same success shape to prevent email enumeration.
    """
    generic_response = MessageResponse(
        message="If an account exists with that email, a reset link has been sent."
    )

    email_lower = body.email.lower().strip()
    result = await db.execute(select(User).where(func.lower(User.email) == email_lower))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return generic_response

    # Generate plaintext token for the email, store only the hash.
    plaintext_token = secrets.token_urlsafe(32)
    user.reset_token = _hash_token(plaintext_token)
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)
    await db.commit()

    # Pick an org for branding (first active membership); fall back to None.
    org_result = await db.execute(
        select(OrganizationUser)
        .where(OrganizationUser.user_id == user.id, OrganizationUser.is_active == True)
        .limit(1)
    )
    org_user = org_result.scalar_one_or_none()
    org_id = org_user.organization_id if org_user else None

    base_url = os.environ.get("FRONTEND_URL", "http://100.121.52.15:7060")
    reset_url = f"{base_url}/reset-password?token={plaintext_token}"

    from src.services.email_service import EmailService
    email_service = EmailService(db)
    try:
        send_result = await email_service.send_password_reset(
            org_id=org_id or "",
            to=user.email,
            user_name=user.first_name or user.email,
            reset_url=reset_url,
            expires_in_hours=RESET_TOKEN_TTL_HOURS,
        )
        if not send_result.success:
            logger.error(f"Password-reset email failed for {user.email}: {send_result.error}")
    except Exception as e:
        logger.exception(f"Password-reset email crashed for {user.email}: {e}")

    return generic_response


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("10/hour")
async def reset_password(
    body: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Consume a reset token and set a new password.

    On success: nulls the token, invalidates all existing sessions,
    and sends a confirmation email.
    """
    from src.core.security import get_password_hash

    token_hash = _hash_token(body.token)
    result = await db.execute(select(User).where(User.reset_token == token_hash))
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not user or not user.reset_token_expires or user.reset_token_expires < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token", "message": "This reset link is invalid or has expired."},
        )

    user.hashed_password = get_password_hash(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    user.failed_login_attempts = 0
    user.locked_until = None

    # Invalidate all existing sessions so an attacker already logged in is ejected.
    sessions_result = await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.is_revoked == False)
        .values(is_revoked=True)
    )
    sessions_invalidated = sessions_result.rowcount or 0

    from src.services.events.platform_event_service import PlatformEventService, Actor
    await PlatformEventService.emit(
        db=db, event_type="user.password_reset_completed",
        level="user_action",
        actor=Actor(actor_type="user", user_id=user.id),
        organization_id=None,
        entity_refs={"user_id": user.id},
        payload={"sessions_invalidated": sessions_invalidated},
    )
    await db.commit()

    # Pick an org for branding.
    org_result = await db.execute(
        select(OrganizationUser)
        .where(OrganizationUser.user_id == user.id, OrganizationUser.is_active == True)
        .limit(1)
    )
    org_user = org_result.scalar_one_or_none()
    org_id = org_user.organization_id if org_user else ""

    from src.services.email_service import EmailService
    email_service = EmailService(db)
    try:
        await email_service.send_password_changed(
            org_id=org_id, to=user.email, user_name=user.first_name or user.email
        )
    except Exception as e:
        logger.exception(f"Password-changed notification failed for {user.email}: {e}")

    return MessageResponse(message="Password updated. You can now sign in.")


@router.post("/recover-email", response_model=RecoverEmailResponse)
@limiter.limit("5/hour")
async def recover_email(
    body: RecoverEmailRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Look up a user by phone and return a masked email hint if matched.

    Anti-enumeration: same response shape whether or not there's a match;
    email_hint is null on no match.
    """
    generic = RecoverEmailResponse(
        message="If an account matches that phone number, a hint is shown below.",
        email_hint=None,
    )
    normalized = _normalize_phone(body.phone)
    if len(normalized) < 7:
        return generic

    # Match by stripping non-digits from stored phone and comparing suffixes.
    # Phones may be stored as "(555) 123-4567" or "+15551234567" — normalize both sides.
    result = await db.execute(
        select(User).where(
            User.phone.isnot(None),
            User.is_active == True,
        )
    )
    candidates = result.scalars().all()
    for u in candidates:
        u_norm = _normalize_phone(u.phone or "")
        if not u_norm:
            continue
        # Match if either normalizes to equal, or one is a suffix of the other (handles +1 prefix variance).
        if u_norm == normalized or u_norm.endswith(normalized) or normalized.endswith(u_norm):
            return RecoverEmailResponse(
                message="We found an account matching that phone number.",
                email_hint=_mask_email(u.email),
            )

    return generic


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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for the logged-in user."""
    from src.core.security import verify_password, get_password_hash

    result = await db.execute(select(User).where(User.id == ctx.user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.hashed_password = get_password_hash(body.new_password)
    await db.commit()
    return MessageResponse(message="Password changed successfully.")


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Update profile for the logged-in user."""
    result = await db.execute(select(User).where(User.id == ctx.user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.first_name is not None:
        user.first_name = body.first_name
    if body.last_name is not None:
        user.last_name = body.last_name
    if body.phone is not None:
        user.phone = body.phone or None
    if body.address is not None:
        user.address = body.address or None
    if body.city is not None:
        user.city = body.city or None
    if body.state is not None:
        user.state = body.state or None
    if body.zip_code is not None:
        user.zip_code = body.zip_code or None

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)
