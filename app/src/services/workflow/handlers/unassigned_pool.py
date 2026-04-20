"""unassigned_pool — dispatch-style post-creation handler.

The job lands with no assignee; the user sees a "dropped in the
unassigned queue" toast + link to the Unassigned filter on the jobs
list. No inline user input needed — emits `handler.applied` as soon
as the frontend renders the toast (frontend handles that; backend
just returns the `pool_count` so the toast can say how many are
waiting).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction
from src.services.events.platform_event_service import Actor
from src.services.workflow.registry import register
from src.services.workflow.types import NextStep


# Open statuses per AgentActionService — everything that isn't done.
_OPEN_STATUSES = ("open", "in_progress")


@register
class UnassignedPoolHandler:
    name = "unassigned_pool"
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
            return None

        pool_count = (await db.execute(
            select(func.count(AgentAction.id))
            .where(
                AgentAction.organization_id == org_id,
                AgentAction.assigned_to.is_(None),
                AgentAction.status.in_(_OPEN_STATUSES),
            )
        )).scalar_one()

        return NextStep(
            kind=self.name,
            initial={
                "entity_type": "job",
                "entity_id": created.id,
                "pool_count": int(pool_count or 0),
            },
        )
