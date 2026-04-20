"""Workflow protocol + response types.

`NextStep` is what handlers return; the frontend uses `kind` to pick a
component from its registry and `initial` as that component's seed
state. Keep `initial` a plain JSON-safe dict so it survives the HTTP
round-trip without custom encoders.

`WorkflowHandler` is the contract each concrete handler fulfills.
Protocols are used (not ABCs) so handler classes can be plain classes
without inheritance boilerplate — matches the lightweight creator
pattern in `src/services/proposals/creators/`.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor


class NextStep(BaseModel):
    """Tells the frontend which inline component to render + its seed state.

    Example:
        NextStep(
            kind="assign_inline",
            initial={
                "entity_type": "job",
                "entity_id": "<uuid>",
                "default_assignee_id": "<uid>",
                "assignee_options": [
                    {"id": "<uid>", "name": "Kim (Manager)"},
                    ...,
                ],
            },
        )
    """

    kind: str
    initial: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class WorkflowHandler(Protocol):
    """Contract every post-creation handler fulfills.

    `name` is the registry key (also the `NextStep.kind` by convention).
    `entity_types` is the tuple of `proposal.entity_type` values this
    handler supports — checked before dispatch so an org can't map an
    unsupported pairing.

    `next_step_for` runs inside the same DB session as the accept; it
    should be read-only (queries to build `initial`). Any mutation
    belongs in the frontend-driven follow-up call.
    """

    name: str
    entity_types: tuple[str, ...]

    async def next_step_for(
        self,
        *,
        created: Any,
        org_id: str,
        actor: Actor,
        db: AsyncSession,
    ) -> Optional[NextStep]:
        ...
