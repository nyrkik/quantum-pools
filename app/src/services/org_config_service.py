"""OrgConfigService — applies scalar org-level configuration changes.

Phase 2 scope: scalar-only settings that already exist as columns on
the `organizations` table. Structured/nested config waits for Phase 4
(post-creation handlers).

The whitelisting here is the structural enforcement of "the product
learns the org" — proposals can only touch settings QP explicitly
considers org-configurable, not arbitrary fields like `created_at` or
`stripe_customer_id`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.models.organization import Organization
from src.services.events.actor_factory import actor_system
from src.services.events.platform_event_service import Actor, PlatformEventService

logger = logging.getLogger(__name__)


# Settings an org_config proposal may change. Paired with a type-check
# function so proposals can't set `agent_enabled = "yes"` (wrong shape).
# Structured/nested settings (e.g., notification routing) are explicitly
# out of scope for Phase 2 and belong to Phase 4.
_ALLOWED: dict[str, type] = {
    "agent_enabled": bool,
    "email_contact_learning": bool,
    "event_retention_days": int,
    "agent_tone_rules": str,
    "agent_signature": str,
    "agent_from_name": str,
    "agent_business_hours_start": int,
    "agent_business_hours_end": int,
    "agent_timezone": str,
}

ALLOWED_KEYS = frozenset(_ALLOWED.keys())


class OrgConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply(
        self,
        *,
        org_id: str,
        key: str,
        value: Any,
        actor: Optional[Actor] = None,
    ) -> Organization:
        """Apply a single scalar setting change. Emits
        `settings.config_changed` event with the (key, before, after) so
        Sonar + audit can reconstruct the change timeline."""
        if key not in _ALLOWED:
            raise ValidationError(
                f"org_config key {key!r} is not in the allowed set "
                f"(scalar-only in Phase 2). Allowed: {sorted(ALLOWED_KEYS)}"
            )
        expected_type = _ALLOWED[key]
        if value is not None and not isinstance(value, expected_type):
            raise ValidationError(
                f"org_config key {key!r} expects {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

        org = await self.db.get(Organization, org_id)
        if org is None:
            raise NotFoundError(f"Organization {org_id} not found")

        before = getattr(org, key, None)
        setattr(org, key, value)
        await self.db.flush()

        # Taxonomy entry: settings.changed with payload {area, fields_changed}.
        # Field NAMES only per taxonomy privacy rule (no before/after values
        # — those could leak PII for string settings like agent_signature).
        await PlatformEventService.emit(
            db=self.db,
            event_type="settings.changed",
            level=("user_action" if actor and actor.actor_type == "user"
                   else "agent_action" if actor and actor.actor_type == "agent"
                   else "system_action"),
            actor=actor or actor_system(),
            organization_id=org_id,
            entity_refs={},
            payload={
                "area": "org_config",
                "fields_changed": [key],
                "source": "proposal_accepted" if actor and actor.actor_type == "user" else "system",
            },
        )
        return org
