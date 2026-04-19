"""Proposal creator: `org_config` entity_type.

Phase 2 scope: scalar settings only. Payload = {key, value} targeting
a single Organization column from the whitelisted set.

Phase 4 will expand this when post-creation handlers need
structured/nested config (e.g., notification routing rules). Keeping
Phase 2 narrow prevents building a speculative schema that Phase 4
rewrites.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor
from src.services.org_config_service import ALLOWED_KEYS, OrgConfigService
from src.services.proposals.registry import register


class OrgConfigProposalPayload(BaseModel):
    """Single-key scalar change. `value` is permissive (Any) because the
    type depends on `key`; OrgConfigService.apply validates type against
    the whitelist. We validate key membership here at stage-time so
    unknown keys fail immediately."""

    key: str = Field(..., description="One of OrgConfigService.ALLOWED_KEYS")
    value: Any

    @field_validator("key")
    @classmethod
    def _key_is_allowed(cls, v: str) -> str:
        if v not in ALLOWED_KEYS:
            raise ValueError(
                f"key {v!r} not in ALLOWED_KEYS ({sorted(ALLOWED_KEYS)})"
            )
        return v


@register("org_config", schema=OrgConfigProposalPayload)
async def create_org_config_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    """Applies a single scalar org setting via the canonical service."""
    return await OrgConfigService(db).apply(
        org_id=org_id,
        actor=actor,
        key=payload["key"],
        value=payload["value"],
    )
