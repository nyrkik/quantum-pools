"""Team management endpoints."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from src.core.database import get_db
from src.core.security import get_password_hash
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrganizationUser, OrgRole
from src.models.user import User
from src.models.tech import Tech
from src.schemas.team import (
    TeamMemberResponse,
    TeamMemberUpdate,
    TeamDeveloperToggle,
    TeamInviteRequest,
)

router = APIRouter(prefix="/team", tags=["team"])

VALID_ROLES = {r.value for r in OrgRole}


async def _get_job_title(db: AsyncSession, org_id: str, user_id: str) -> str | None:
    result = await db.execute(
        select(Tech.job_title).where(
            Tech.organization_id == org_id, Tech.user_id == user_id, Tech.is_active == True
        )
    )
    return result.scalar_one_or_none()


def _to_response(ou: OrganizationUser, job_title: str | None = None) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=ou.id,
        user_id=ou.user_id,
        email=ou.user.email,
        first_name=ou.user.first_name,
        last_name=ou.user.last_name,
        phone=ou.user.phone,
        address=ou.user.address,
        city=ou.user.city,
        state=ou.user.state,
        zip_code=ou.user.zip_code,
        role=ou.role.value,
        job_title=job_title,
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

    # Fetch job titles from tech records linked via user_id
    user_ids = [m.user_id for m in members]
    tech_result = await db.execute(
        select(Tech.user_id, Tech.job_title)
        .where(Tech.organization_id == ctx.organization_id, Tech.user_id.in_(user_ids), Tech.is_active == True)
    )
    title_map = {row.user_id: row.job_title for row in tech_result.all()}

    return [_to_response(m, job_title=title_map.get(m.user_id)) for m in members]


@router.post("/invite", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: TeamInviteRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}")
    # Full Access can only be assigned by existing Full Access users
    if body.role == "owner" and ctx.role not in (OrgRole.owner, OrgRole.admin):
        raise HTTPException(status_code=403, detail="Only Full Access or Admin users can grant Full Access")

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

    # Reuse existing token if present, only generate new if missing
    if not member.user.verification_token:
        member.user.verification_token = secrets.token_urlsafe(48)
        await db.commit()

    try:
        await _send_invite_email(member.user, ctx.organization_id, db)
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(f"Resend invite failed: {traceback.format_exc()}")
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

    # Full Access users can only be modified by other Full Access users
    if member.role == OrgRole.owner and ctx.role != OrgRole.owner:
        raise HTTPException(status_code=403, detail="Only Full Access users can modify other Full Access accounts")

    # Can't demote yourself if you're the ONLY Full Access user (prevent lockout)
    if member.user_id == ctx.user.id and member.role == OrgRole.owner and body.role and body.role != "owner":
        other_owners = await db.execute(
            select(func.count(OrganizationUser.id)).where(
                OrganizationUser.organization_id == ctx.organization_id,
                OrganizationUser.role == OrgRole.owner,
                OrganizationUser.is_active == True,
                OrganizationUser.id != member.id,
            )
        )
        if (other_owners.scalar() or 0) == 0:
            raise HTTPException(status_code=400, detail="Cannot demote yourself — you are the only Full Access user. Grant Full Access to another member first.")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}")
        if body.role == "owner" and ctx.role not in (OrgRole.owner, OrgRole.admin):
            raise HTTPException(status_code=403, detail="Only Full Access or Admin users can grant Full Access")
        member.role = OrgRole(body.role)
        member.role_version = (member.role_version or 0) + 1
        member.permission_version = (member.permission_version or 0) + 1

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
    if body.address is not None:
        member.user.address = body.address
    if body.city is not None:
        member.user.city = body.city
    if body.state is not None:
        member.user.state = body.state
    if body.zip_code is not None:
        member.user.zip_code = body.zip_code

    await db.commit()
    await db.refresh(member)

    # Invalidate permission cache if role changed
    if body.role is not None:
        from src.services.permission_service import PermissionService
        await PermissionService(db).invalidate_cache(member.id)

    title = await _get_job_title(db, ctx.organization_id, member.user_id)
    return _to_response(member, job_title=title)


@router.put("/{member_id}/developer", response_model=TeamMemberResponse)
async def toggle_developer(
    member_id: str,
    body: TeamDeveloperToggle,
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

    member.is_developer = body.is_developer
    await db.commit()
    await db.refresh(member)
    title = await _get_job_title(db, ctx.organization_id, member.user_id)
    return _to_response(member, job_title=title)


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

    if member.user_id == ctx.user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    # If removing a Full Access user, ensure at least one remains
    if member.role == OrgRole.owner:
        if ctx.role != OrgRole.owner:
            raise HTTPException(status_code=403, detail="Only Full Access users can remove other Full Access accounts")
        other_owners = await db.execute(
            select(func.count(OrganizationUser.id)).where(
                OrganizationUser.organization_id == ctx.organization_id,
                OrganizationUser.role == OrgRole.owner,
                OrganizationUser.is_active == True,
                OrganizationUser.id != member.id,
            )
        )
        if (other_owners.scalar() or 0) == 0:
            raise HTTPException(status_code=400, detail="Cannot remove the last Full Access user")

    await db.delete(member)
    await db.commit()


async def _send_invite_email(user: User, organization_id: str, db: AsyncSession):
    """Send account setup email to invited user."""
    import os
    from src.services.email_service import EmailService

    base_url = os.environ.get("FRONTEND_URL", "http://100.121.52.15:7060")
    setup_url = f"{base_url}/setup-account?token={user.verification_token}&email={user.email}"

    email_service = EmailService(db)
    result = await email_service.send_team_invite(
        org_id=organization_id,
        to=user.email,
        user_name=user.first_name,
        setup_url=setup_url,
    )
    if not result.success:
        raise RuntimeError(result.error or "Email send failed")
