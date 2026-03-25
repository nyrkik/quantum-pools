"""Permission resolution service with Redis caching."""

import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.permission import Permission
from src.models.permission_preset import PermissionPreset
from src.models.preset_permission import PresetPermission
from src.models.org_role import OrgRole
from src.models.org_role_permission import OrgRolePermission
from src.models.user_permission_override import UserPermissionOverride
from src.models.organization_user import OrganizationUser
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes


def _scope_level(scope: str) -> int:
    """Map scope string to numeric level for comparison."""
    return {"own": 1, "team": 2, "all": 3}.get(scope, 0)


class PermissionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_permissions(self, org_user: OrganizationUser) -> dict[str, str]:
        """Returns {permission_slug: scope} for the user. Uses Redis cache."""
        cache_key = f"perms:{org_user.id}:{org_user.permission_version}"

        # Try cache
        redis = await get_redis()
        if redis:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache read failed: {e}")

        # 1. Base permissions from custom role or preset
        if org_user.org_role_id:
            base = await self._get_custom_role_permissions(org_user.org_role_id)
        else:
            base = await self._get_preset_permissions(org_user.role.value)

        # 2. Apply per-user overrides
        overrides = await self._get_user_overrides(org_user.id)

        result = dict(base)
        for slug, (scope, granted) in overrides.items():
            if granted:
                if slug not in result or _scope_level(scope) > _scope_level(result[slug]):
                    result[slug] = scope
            else:
                result.pop(slug, None)

        # Cache result
        if redis:
            try:
                await redis.set(cache_key, json.dumps(result), ex=_CACHE_TTL)
            except Exception as e:
                logger.warning(f"Redis cache write failed: {e}")

        return result

    async def _get_preset_permissions(self, preset_slug: str) -> dict[str, str]:
        """Get permissions for a system preset by slug."""
        result = await self.db.execute(
            select(Permission.slug, PresetPermission.scope)
            .join(PresetPermission, PresetPermission.permission_id == Permission.id)
            .join(PermissionPreset, PermissionPreset.id == PresetPermission.preset_id)
            .where(PermissionPreset.slug == preset_slug)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _get_custom_role_permissions(self, org_role_id: str) -> dict[str, str]:
        """Get permissions for a custom org role."""
        result = await self.db.execute(
            select(Permission.slug, OrgRolePermission.scope)
            .join(OrgRolePermission, OrgRolePermission.permission_id == Permission.id)
            .where(OrgRolePermission.org_role_id == org_role_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _get_user_overrides(self, org_user_id: str) -> dict[str, tuple[str, bool]]:
        """Get per-user permission overrides. Returns {slug: (scope, granted)}."""
        result = await self.db.execute(
            select(Permission.slug, UserPermissionOverride.scope, UserPermissionOverride.granted)
            .join(UserPermissionOverride, UserPermissionOverride.permission_id == Permission.id)
            .where(UserPermissionOverride.org_user_id == org_user_id)
        )
        return {row[0]: (row[1], row[2]) for row in result.all()}

    async def invalidate_cache(self, org_user_id: str):
        """Invalidate cached permissions for a user (call after override/role changes)."""
        redis = await get_redis()
        if redis:
            try:
                # Delete all keys matching this user (any permission_version)
                async for key in redis.scan_iter(f"perms:{org_user_id}:*"):
                    await redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis cache invalidation failed: {e}")

    async def get_all_permissions_grouped(self) -> dict[str, list[dict]]:
        """Get all permissions grouped by resource."""
        result = await self.db.execute(
            select(Permission).order_by(Permission.sort_order)
        )
        perms = result.scalars().all()
        grouped: dict[str, list[dict]] = {}
        for p in perms:
            grouped.setdefault(p.resource, []).append({
                "slug": p.slug,
                "action": p.action,
                "description": p.description,
            })
        return grouped
