"""assign_inline — the default job post-creation handler.

After a proposal creates a job, the user sees an inline assignee
picker with a pre-selected default. Save posts to the canonical
`PUT /agent-actions/{id}` endpoint; Skip emits `handler.abandoned`.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction
from src.models.org_workflow_config import OrgWorkflowConfig
from src.services.events.platform_event_service import Actor
from src.services.workflow.handlers._assignee import (
    load_assignee_options,
    resolve_default_assignee,
)
from src.services.workflow.registry import register
from src.services.workflow.types import NextStep


# System default strategy — mirrors the migration/model fallback so a
# missing org_workflow_config row still resolves cleanly.
_SYSTEM_DEFAULT_STRATEGY = {"strategy": "last_used_in_org"}


@register
class AssignInlineHandler:
    name = "assign_inline"
    entity_types = ("job",)

    async def next_step_for(
        self,
        *,
        created: Any,
        org_id: str,
        actor: Actor,
        db: AsyncSession,
    ) -> Optional[NextStep]:
        if not isinstance(created, AgentAction):
            # Shouldn't happen — entity_types guards against this — but
            # fail quiet if the registry gets misconfigured.
            return None

        strategy = await self._load_strategy(org_id, db)
        options = await load_assignee_options(org_id, db)
        default_id = await resolve_default_assignee(
            strategy=strategy,
            org_id=org_id,
            actor_user_id=actor.user_id,
            db=db,
        )
        # If the resolved default isn't in the options (e.g., left the
        # org), drop the default rather than pre-selecting a missing
        # user.
        if default_id and not any(o["id"] == default_id for o in options):
            default_id = None

        return NextStep(
            kind=self.name,
            initial={
                "entity_type": "job",
                "entity_id": created.id,
                "default_assignee_id": default_id,
                "assignee_options": options,
            },
        )

    async def _load_strategy(self, org_id: str, db: AsyncSession) -> dict:
        row = await db.get(OrgWorkflowConfig, org_id)
        if row is None or not row.default_assignee_strategy:
            return _SYSTEM_DEFAULT_STRATEGY
        return row.default_assignee_strategy
