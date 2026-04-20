"""WorkflowConfigService — read/write the per-org handler config and
dispatch the post-creation `next_step` from an accept response.

Rows are lazy-created: `get_or_default` returns the hardcoded system
default when no row exists, and `put` inserts or updates in place.
Every write emits `workflow_config.changed` with the before/after
snapshot so the platform_events stream + workflow_observer (Phase 6)
can see how orgs evolve their configs.

Handler lookup failure never rolls back the accept — a swallowed
exception + None return leaves the user on the non-augmented path.
See docs/ai-platform-phase-4.md §4.2.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_proposal import AgentProposal
from src.models.org_workflow_config import OrgWorkflowConfig
from src.services.events.platform_event_service import Actor, PlatformEventService
from src.services.workflow.registry import get_handler
from src.services.workflow.types import NextStep

logger = logging.getLogger(__name__)


# The shape an org without a configured row sees. Keep in sync with
# the migration/model defaults + the spec §5.2.
SYSTEM_DEFAULTS: dict[str, Any] = {
    "post_creation_handlers": {"job": "assign_inline"},
    "default_assignee_strategy": {"strategy": "last_used_in_org"},
}


class UnknownHandlerError(Exception):
    """Raised by `put` when the incoming config references a handler
    name the registry doesn't know. Message lists the known names so
    the caller can surface an actionable 422."""


class WorkflowConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_or_default(self, org_id: str) -> dict:
        """Return the org's config merged with system defaults — caller
        sees the effective shape regardless of whether a row exists."""
        row = await self.db.get(OrgWorkflowConfig, org_id)
        if row is None:
            return copy.deepcopy(SYSTEM_DEFAULTS)

        return {
            "post_creation_handlers": dict(SYSTEM_DEFAULTS["post_creation_handlers"]) | (row.post_creation_handlers or {}),
            "default_assignee_strategy": row.default_assignee_strategy or copy.deepcopy(SYSTEM_DEFAULTS["default_assignee_strategy"]),
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def put(
        self,
        *,
        org_id: str,
        post_creation_handlers: dict[str, str],
        default_assignee_strategy: dict,
        actor: Actor,
    ) -> dict:
        """Upsert the org's config. Validates handler names against the
        registry before touching the DB. Emits `workflow_config.changed`
        on success."""
        # Validate handler names.
        from src.services.workflow.registry import HANDLERS
        for entity_type, handler_name in (post_creation_handlers or {}).items():
            if handler_name not in HANDLERS:
                raise UnknownHandlerError(
                    f"Unknown handler {handler_name!r} for entity_type={entity_type!r}. "
                    f"Known: {sorted(HANDLERS)}"
                )
            # Cross-check: handler supports this entity_type.
            h = HANDLERS[handler_name]
            if entity_type not in h.entity_types:
                raise UnknownHandlerError(
                    f"Handler {handler_name!r} does not support entity_type={entity_type!r}. "
                    f"Supported: {list(h.entity_types)}"
                )

        before = await self.get_or_default(org_id)

        row = await self.db.get(OrgWorkflowConfig, org_id)
        if row is None:
            row = OrgWorkflowConfig(
                organization_id=org_id,
                post_creation_handlers=post_creation_handlers or {},
                default_assignee_strategy=default_assignee_strategy or copy.deepcopy(
                    SYSTEM_DEFAULTS["default_assignee_strategy"]
                ),
                updated_by_user_id=actor.user_id,
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(row)
        else:
            row.post_creation_handlers = post_creation_handlers or {}
            row.default_assignee_strategy = default_assignee_strategy or row.default_assignee_strategy
            row.updated_by_user_id = actor.user_id
            row.updated_at = datetime.now(timezone.utc)

        await self.db.flush()

        after = await self.get_or_default(org_id)

        # Non-blocking audit emit.
        try:
            await PlatformEventService.emit(
                db=self.db,
                event_type="workflow_config.changed",
                level="user_action",
                actor=actor,
                organization_id=org_id,
                entity_refs={},
                payload={"before": before, "after": after},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("workflow_config.changed emit failed: %s", e)

        return after

    # ------------------------------------------------------------------
    # Dispatch (called from the proposals.accept router)
    # ------------------------------------------------------------------

    async def resolve_next_step(
        self,
        *,
        proposal: AgentProposal,
        created: Any,
        org_id: str,
        actor: Actor,
    ) -> Optional[dict]:
        """Look up the handler configured for this org + entity_type
        and ask it for a NextStep. Returns a plain dict (JSON-ready)
        or None. Never raises — all failures are logged and swallowed
        so the accept response still returns with `next_step: null`.
        """
        try:
            config = await self.get_or_default(org_id)
            handler_name = config["post_creation_handlers"].get(
                proposal.entity_type
            )
            if not handler_name:
                return None

            handler = get_handler(handler_name)
            if proposal.entity_type not in handler.entity_types:
                logger.warning(
                    "workflow: handler %s does not support entity_type %s (org=%s) — skipping",
                    handler_name, proposal.entity_type, org_id,
                )
                return None

            step: Optional[NextStep] = await handler.next_step_for(
                created=created, org_id=org_id, actor=actor, db=self.db,
            )
            if step is None:
                return None
            return step.model_dump(mode="json")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "workflow.resolve_next_step failed for proposal=%s org=%s: %s",
                proposal.id, org_id, e,
            )
            return None
