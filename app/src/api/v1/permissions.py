"""Permission catalog, presets, custom roles, and user overrides API."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrganizationUser, OrgRole as OrgRoleEnum
from src.models.permission import Permission
from src.models.permission_preset import PermissionPreset
from src.models.preset_permission import PresetPermission
from src.models.org_role import OrgRole
from src.models.org_role_permission import OrgRolePermission
from src.models.user_permission_override import UserPermissionOverride
from src.services.permission_service import PermissionService

router = APIRouter(prefix="/permissions", tags=["permissions"])


# ── Schemas ──────────────────────────────────────────────────────────

class PermissionItem(BaseModel):
    slug: str
    action: str
    description: str | None = None

class PermissionCatalogResponse(BaseModel):
    resources: dict[str, list[PermissionItem]]

class PresetPermissionItem(BaseModel):
    slug: str
    scope: str

class PresetResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    is_system: bool = True
    sort_order: int = 0
    permissions: list[PresetPermissionItem] = []

class OrgRolePermissionItem(BaseModel):
    slug: str
    scope: str = "all"

class CreateOrgRoleRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    based_on_preset_slug: str | None = None
    permissions: list[OrgRolePermissionItem] = []

class UpdateOrgRoleRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[OrgRolePermissionItem] | None = None

class OrgRoleResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    based_on_preset_id: str | None = None
    is_active: bool = True
    permissions: list[OrgRolePermissionItem] = []
    created_at: datetime
    updated_at: datetime

class OverrideItem(BaseModel):
    slug: str
    scope: str = "all"
    granted: bool = True

class EffectivePermissionsResponse(BaseModel):
    org_user_id: str
    role: str
    org_role_id: str | None = None
    permissions: dict[str, str]

class OverridesResponse(BaseModel):
    org_user_id: str
    overrides: list[OverrideItem]


# ── Catalog ──────────────────────────────────────────────────────────

@router.get("/catalog", response_model=PermissionCatalogResponse)
async def get_permission_catalog(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all permission slugs grouped by resource."""
    service = PermissionService(db)
    grouped = await service.get_all_permissions_grouped()
    return PermissionCatalogResponse(
        resources={
            resource: [PermissionItem(**p) for p in perms]
            for resource, perms in grouped.items()
        }
    )


# ── Presets ──────────────────────────────────────────────────────────

@router.get("/presets", response_model=list[PresetResponse])
async def list_presets(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all permission presets with their permission mappings."""
    result = await db.execute(
        select(PermissionPreset)
        .options(selectinload(PermissionPreset.permissions))
        .order_by(PermissionPreset.sort_order)
    )
    presets = result.scalars().unique().all()

    # Load permission slugs for each preset
    responses = []
    for preset in presets:
        perm_ids = [pp.permission_id for pp in preset.permissions]
        slug_map: dict[str, str] = {}
        if perm_ids:
            perm_result = await db.execute(
                select(Permission.id, Permission.slug).where(Permission.id.in_(perm_ids))
            )
            slug_map = {row[0]: row[1] for row in perm_result.all()}

        responses.append(PresetResponse(
            id=preset.id, slug=preset.slug, name=preset.name,
            description=preset.description, is_system=preset.is_system,
            sort_order=preset.sort_order,
            permissions=[
                PresetPermissionItem(slug=slug_map.get(pp.permission_id, ""), scope=pp.scope)
                for pp in preset.permissions if pp.permission_id in slug_map
            ],
        ))
    return responses


@router.get("/presets/{slug}", response_model=PresetResponse)
async def get_preset(
    slug: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single preset with its permissions."""
    result = await db.execute(
        select(PermissionPreset)
        .options(selectinload(PermissionPreset.permissions))
        .where(PermissionPreset.slug == slug)
    )
    preset = result.scalars().unique().first()
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    perm_ids = [pp.permission_id for pp in preset.permissions]
    slug_map: dict[str, str] = {}
    if perm_ids:
        perm_result = await db.execute(
            select(Permission.id, Permission.slug).where(Permission.id.in_(perm_ids))
        )
        slug_map = {row[0]: row[1] for row in perm_result.all()}

    return PresetResponse(
        id=preset.id, slug=preset.slug, name=preset.name,
        description=preset.description, is_system=preset.is_system,
        sort_order=preset.sort_order,
        permissions=[
            PresetPermissionItem(slug=slug_map.get(pp.permission_id, ""), scope=pp.scope)
            for pp in preset.permissions if pp.permission_id in slug_map
        ],
    )


# ── Custom Org Roles ─────────────────────────────────────────────────

async def _require_role_management(ctx: OrgUserContext, db: AsyncSession):
    """Check that user can manage roles (owner/admin or has settings.edit)."""
    if ctx.role in (OrgRoleEnum.owner, OrgRoleEnum.admin):
        return
    perms = await ctx.load_permissions(db)
    if "settings.edit" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "insufficient_permissions", "permission": "settings.edit"},
        )


@router.get("/roles", response_model=list[OrgRoleResponse])
async def list_org_roles(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List custom roles for the current organization."""
    await _require_role_management(ctx, db)
    result = await db.execute(
        select(OrgRole)
        .options(selectinload(OrgRole.permissions))
        .where(OrgRole.organization_id == ctx.organization_id, OrgRole.is_active == True)
        .order_by(OrgRole.name)
    )
    roles = result.scalars().unique().all()
    return [await _role_to_response(db, r) for r in roles]


@router.post("/roles", response_model=OrgRoleResponse, status_code=201)
async def create_org_role(
    body: CreateOrgRoleRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom role for the organization."""
    await _require_role_management(ctx, db)

    # Check slug uniqueness
    existing = await db.execute(
        select(OrgRole).where(
            OrgRole.organization_id == ctx.organization_id,
            OrgRole.slug == body.slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Role slug '{body.slug}' already exists")

    # Resolve preset if provided
    based_on_preset_id = None
    if body.based_on_preset_slug:
        preset_result = await db.execute(
            select(PermissionPreset.id).where(PermissionPreset.slug == body.based_on_preset_slug)
        )
        based_on_preset_id = preset_result.scalar_one_or_none()

    role = OrgRole(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        based_on_preset_id=based_on_preset_id,
    )
    db.add(role)
    await db.flush()

    # Add permissions
    await _set_role_permissions(db, role.id, body.permissions)
    await db.commit()

    # Re-fetch with permissions loaded
    result = await db.execute(
        select(OrgRole).options(selectinload(OrgRole.permissions)).where(OrgRole.id == role.id)
    )
    role = result.scalars().unique().first()
    return await _role_to_response(db, role)


@router.get("/roles/{role_id}", response_model=OrgRoleResponse)
async def get_org_role(
    role_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a custom role with its permissions."""
    await _require_role_management(ctx, db)
    result = await db.execute(
        select(OrgRole)
        .options(selectinload(OrgRole.permissions))
        .where(OrgRole.id == role_id, OrgRole.organization_id == ctx.organization_id)
    )
    role = result.scalars().unique().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return await _role_to_response(db, role)


@router.put("/roles/{role_id}", response_model=OrgRoleResponse)
async def update_org_role(
    role_id: str,
    body: UpdateOrgRoleRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom role's name, description, and/or permissions."""
    await _require_role_management(ctx, db)
    result = await db.execute(
        select(OrgRole).where(OrgRole.id == role_id, OrgRole.organization_id == ctx.organization_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    role.updated_at = datetime.now(timezone.utc)

    if body.permissions is not None:
        await _set_role_permissions(db, role.id, body.permissions)

    await db.commit()

    # Re-fetch
    result = await db.execute(
        select(OrgRole).options(selectinload(OrgRole.permissions)).where(OrgRole.id == role.id)
    )
    role = result.scalars().unique().first()
    return await _role_to_response(db, role)


@router.delete("/roles/{role_id}")
async def delete_org_role(
    role_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a custom role (set is_active=False)."""
    await _require_role_management(ctx, db)
    result = await db.execute(
        select(OrgRole).where(OrgRole.id == role_id, OrgRole.organization_id == ctx.organization_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    role.is_active = False
    role.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Role deactivated"}


# ── User Effective Permissions ───────────────────────────────────────

@router.get("/users/{org_user_id}/effective", response_model=EffectivePermissionsResponse)
async def get_effective_permissions(
    org_user_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get resolved permissions for a specific org user."""
    await _require_role_management(ctx, db)
    target = await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.id == org_user_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    org_user = target.scalar_one_or_none()
    if not org_user:
        raise HTTPException(status_code=404, detail="Organization user not found")

    service = PermissionService(db)
    perms = await service.resolve_permissions(org_user)
    return EffectivePermissionsResponse(
        org_user_id=org_user_id,
        role=org_user.role.value,
        org_role_id=org_user.org_role_id,
        permissions=perms,
    )


# ── User Overrides ──────────────────────────────────────────────────

@router.get("/users/{org_user_id}/overrides", response_model=OverridesResponse)
async def get_user_overrides(
    org_user_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current permission overrides for a user."""
    await _require_role_management(ctx, db)
    target = await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.id == org_user_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    if not target.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Organization user not found")

    result = await db.execute(
        select(Permission.slug, UserPermissionOverride.scope, UserPermissionOverride.granted)
        .join(UserPermissionOverride, UserPermissionOverride.permission_id == Permission.id)
        .where(UserPermissionOverride.org_user_id == org_user_id)
    )
    overrides = [
        OverrideItem(slug=row[0], scope=row[1], granted=row[2])
        for row in result.all()
    ]
    return OverridesResponse(org_user_id=org_user_id, overrides=overrides)


@router.put("/users/{org_user_id}/overrides", response_model=OverridesResponse)
async def set_user_overrides(
    org_user_id: str,
    overrides: list[OverrideItem],
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace all permission overrides for a user."""
    await _require_role_management(ctx, db)
    target = await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.id == org_user_id,
            OrganizationUser.organization_id == ctx.organization_id,
        )
    )
    org_user = target.scalar_one_or_none()
    if not org_user:
        raise HTTPException(status_code=404, detail="Organization user not found")

    # Resolve permission slugs to IDs
    slugs = [o.slug for o in overrides]
    perm_result = await db.execute(
        select(Permission.slug, Permission.id).where(Permission.slug.in_(slugs))
    )
    slug_to_id = {row[0]: row[1] for row in perm_result.all()}

    # Validate all slugs exist
    unknown = set(slugs) - set(slug_to_id.keys())
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission slugs: {', '.join(unknown)}")

    # Delete existing overrides
    await db.execute(
        delete(UserPermissionOverride).where(UserPermissionOverride.org_user_id == org_user_id)
    )

    # Insert new overrides
    for o in overrides:
        db.add(UserPermissionOverride(
            id=str(uuid.uuid4()),
            org_user_id=org_user_id,
            permission_id=slug_to_id[o.slug],
            scope=o.scope,
            granted=o.granted,
        ))

    # Bump permission_version
    org_user.permission_version = (org_user.permission_version or 0) + 1

    # Commit first, THEN invalidate cache to avoid race condition
    await db.commit()

    # Invalidate Redis cache
    service = PermissionService(db)
    await service.invalidate_cache(org_user_id)

    return OverridesResponse(org_user_id=org_user_id, overrides=overrides)


# ── Helpers ──────────────────────────────────────────────────────────

async def _set_role_permissions(db: AsyncSession, role_id: str, permissions: list[OrgRolePermissionItem]):
    """Replace all permissions for a custom role."""
    # Delete existing
    await db.execute(
        delete(OrgRolePermission).where(OrgRolePermission.org_role_id == role_id)
    )

    if not permissions:
        return

    # Resolve slugs to IDs
    slugs = [p.slug for p in permissions]
    perm_result = await db.execute(
        select(Permission.slug, Permission.id).where(Permission.slug.in_(slugs))
    )
    slug_to_id = {row[0]: row[1] for row in perm_result.all()}

    unknown = set(slugs) - set(slug_to_id.keys())
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission slugs: {', '.join(unknown)}")

    for p in permissions:
        db.add(OrgRolePermission(
            org_role_id=role_id,
            permission_id=slug_to_id[p.slug],
            scope=p.scope,
        ))


async def _role_to_response(db: AsyncSession, role: OrgRole) -> OrgRoleResponse:
    """Convert OrgRole model to response with permission slugs."""
    perm_ids = [rp.permission_id for rp in role.permissions]
    slug_map: dict[str, str] = {}
    if perm_ids:
        perm_result = await db.execute(
            select(Permission.id, Permission.slug).where(Permission.id.in_(perm_ids))
        )
        slug_map = {row[0]: row[1] for row in perm_result.all()}

    return OrgRoleResponse(
        id=role.id,
        slug=role.slug,
        name=role.name,
        description=role.description,
        based_on_preset_id=role.based_on_preset_id,
        is_active=role.is_active,
        permissions=[
            OrgRolePermissionItem(slug=slug_map.get(rp.permission_id, ""), scope=rp.scope)
            for rp in role.permissions if rp.permission_id in slug_map
        ],
        created_at=role.created_at,
        updated_at=role.updated_at,
    )
