"""Team management endpoints."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import get_db
from src.core.security import get_password_hash
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrganizationUser, OrgRole
from src.models.user import User
from src.schemas.team import (
    TeamMemberResponse,
    TeamMemberUpdate,
    TeamDeveloperToggle,
    TeamInviteRequest,
)

router = APIRouter(prefix="/team", tags=["team"])

VALID_ROLES = {r.value for r in OrgRole}


def _to_response(ou: OrganizationUser) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=ou.id,
        user_id=ou.user_id,
        email=ou.user.email,
        first_name=ou.user.first_name,
        last_name=ou.user.last_name,
        phone=ou.user.phone,
        role=ou.role.value,
        is_developer=ou.is_developer,
        is_active=ou.is_active,
        is_verified=ou.user.is_verified,
        last_login=ou.user.last_login,
        created_at=ou.created_at,
    )


@router.get("", response_model=list[TeamMemberResponse])
async def list_team(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.user))
        .where(OrganizationUser.organization_id == ctx.organization_id)
        .order_by(OrganizationUser.created_at)
    )
    members = result.unique().scalars().all()
    return [_to_response(m) for m in members]


@router.post("/invite", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: TeamInviteRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}")
    if body.role == "owner" and ctx.role != OrgRole.owner:
        raise HTTPException(status_code=403, detail="Only owner can assign owner role")

    # Check if user already exists
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user:
        # Check if already a member
        result = await db.execute(
            select(OrganizationUser).where(
                OrganizationUser.user_id == user.id,
                OrganizationUser.organization_id == ctx.organization_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="User is already a team member")
    else:
        # Create user with a random temporary password and a setup token
        temp_password = secrets.token_urlsafe(32)
        setup_token = secrets.token_urlsafe(48)

        user = User(
            email=body.email,
            hashed_password=get_password_hash(temp_password),
            first_name=body.first_name,
            last_name=body.last_name,
            phone=body.phone,
            is_verified=False,
            verification_token=setup_token,
        )
        db.add(user)
        await db.flush()

    org_user = OrganizationUser(
        user_id=user.id,
        organization_id=ctx.organization_id,
        role=OrgRole(body.role),
    )
    db.add(org_user)
    await db.commit()

    # Reload with user relationship
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.user))
        .where(OrganizationUser.id == org_user.id)
    )
    org_user = result.unique().scalar_one()

    # Send invitation email
    if user.verification_token:
        try:
            await _send_invite_email(user, ctx.organization_id, db)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to send invite email to {user.email}: {e}")

    return _to_response(org_user)


@router.post("/{member_id}/resend-invite")
async def resend_invite(
    member_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Resend invite email to a team member who hasn't set up their account."""
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.user))
        .where(
            OrganizationUser.id == member_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    member = result.unique().scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member.user.is_verified:
        raise HTTPException(status_code=400, detail="User has already set up their account")

    # Generate new token
    member.user.verification_token = secrets.token_urlsafe(48)
    await db.commit()

    try:
        await _send_invite_email(member.user, ctx.organization_id, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    return {"sent": True}


@router.put("/{member_id}", response_model=TeamMemberResponse)
async def update_member(
    member_id: str,
    body: TeamMemberUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.user))
        .where(
            OrganizationUser.id == member_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    member = result.unique().scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Can't modify owner unless you are owner
    if member.role == OrgRole.owner and ctx.role != OrgRole.owner:
        raise HTTPException(status_code=403, detail="Only owner can modify owner accounts")

    # Can't demote yourself from owner (prevent lockout)
    if member.user_id == ctx.user.id and member.role == OrgRole.owner and body.role and body.role != "owner":
        raise HTTPException(status_code=400, detail="Cannot demote yourself from owner")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}")
        if body.role == "owner" and ctx.role != OrgRole.owner:
            raise HTTPException(status_code=403, detail="Only owner can assign owner role")
        member.role = OrgRole(body.role)

    if body.is_active is not None:
        if member.user_id == ctx.user.id:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        member.is_active = body.is_active

    # Update user details
    if body.first_name is not None:
        member.user.first_name = body.first_name
    if body.last_name is not None:
        member.user.last_name = body.last_name
    if body.phone is not None:
        member.user.phone = body.phone

    await db.commit()
    await db.refresh(member)
    return _to_response(member)


@router.put("/{member_id}/developer", response_model=TeamMemberResponse)
async def toggle_developer(
    member_id: str,
    body: TeamDeveloperToggle,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrganizationUser)
        .options(joinedload(OrganizationUser.user))
        .where(
            OrganizationUser.id == member_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    member = result.unique().scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member.is_developer = body.is_developer
    await db.commit()
    await db.refresh(member)
    return _to_response(member)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.id == member_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member.role == OrgRole.owner:
        raise HTTPException(status_code=400, detail="Cannot remove owner")

    if member.user_id == ctx.user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    await db.delete(member)
    await db.commit()


async def _send_invite_email(user: User, organization_id: str, db: AsyncSession):
    """Send account setup email to invited user."""
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import os

    from src.models.organization import Organization
    result = await db.execute(select(Organization).where(Organization.id == organization_id))
    org = result.scalar_one_or_none()
    org_name = org.name if org else "QuantumPools"

    # Build setup URL — frontend handles the token
    base_url = os.environ.get("FRONTEND_URL", "http://100.121.52.15:7060")
    setup_url = f"{base_url}/setup-account?token={user.verification_token}&email={user.email}"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{org_name} <contact@sapphire-pools.com>"
    msg["To"] = user.email
    msg["Subject"] = f"You've been invited to {org_name}"

    text = f"""Hi {user.first_name},

You've been invited to join {org_name} on QuantumPools.

Click the link below to set up your password and access your account:

{setup_url}

This link will expire in 7 days. If you have questions, reply to this email.

— {org_name}"""

    html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 500px; margin: 0 auto; padding: 32px 0;">
<h2 style="color: #1a1a2e; margin-bottom: 8px;">Welcome to {org_name}</h2>
<p style="color: #4a5568; line-height: 1.6;">Hi {user.first_name},</p>
<p style="color: #4a5568; line-height: 1.6;">You've been invited to join <strong>{org_name}</strong> on QuantumPools.</p>
<p style="margin: 24px 0;">
  <a href="{setup_url}" style="background: #1a1a2e; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">Set Up Your Account</a>
</p>
<p style="color: #718096; font-size: 0.875rem;">This link expires in 7 days. If the button doesn't work, copy this URL:<br>
<span style="color: #4a5568; word-break: break-all;">{setup_url}</span></p>
</div>"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    smtp_host = os.environ.get("AGENT_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("AGENT_SMTP_PORT", "587"))
    smtp_user = os.environ.get("AGENT_GMAIL_USER", "")
    smtp_pass = os.environ.get("AGENT_GMAIL_PASSWORD", "")

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_user,
        password=smtp_pass,
        start_tls=True,
    )
