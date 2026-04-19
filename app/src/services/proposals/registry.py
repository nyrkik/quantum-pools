"""Entity-type registry for the proposals system.

Each entity_type (e.g., "job", "estimate", "equipment_item") has its own
creator module under `src/services/proposals/creators/<entity_type>.py`.
The creator registers itself at import time via the `@register` decorator.

`ProposalService.accept` looks up the creator here, calls it with the
proposal's `proposed_payload` + org_id + actor + db session, and the
creator returns the freshly-created entity.

This split (registry separate from service) keeps proposal-state logic
in one place and entity-specific logic in another — each creator can be
added or modified without touching ProposalService.

See `docs/ai-platform-phase-2.md` §6.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional, Type

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor

logger = logging.getLogger(__name__)


# A creator takes the validated payload, org scope, actor, and db session,
# and returns the created entity (caller decides what to do with it —
# ProposalService stores (type, id) via outcome_entity_*).
CreatorFn = Callable[[dict, str, Actor, AsyncSession], Awaitable[Any]]


class _RegistryEntry:
    """A creator + its payload schema. Schema is optional but encouraged —
    stage-time validation catches malformed AI output before it sits in
    the DB as a broken proposal."""

    __slots__ = ("creator", "schema", "outcome_entity_type")

    def __init__(
        self,
        creator: CreatorFn,
        schema: Optional[Type[BaseModel]],
        outcome_entity_type: str,
    ):
        self.creator = creator
        self.schema = schema
        self.outcome_entity_type = outcome_entity_type


# Module-global registry. Populated via `@register(...)` at import time.
_REGISTRY: dict[str, _RegistryEntry] = {}


def register(
    entity_type: str,
    *,
    schema: Optional[Type[BaseModel]] = None,
    outcome_entity_type: Optional[str] = None,
):
    """Decorator: register a creator for an entity_type.

    Args:
        entity_type: the string stored in `agent_proposals.entity_type`
            (e.g., "job", "estimate"). Must match the creator's domain.
        schema: Pydantic model for stage-time payload validation. None
            skips validation; prefer providing one.
        outcome_entity_type: what `agent_proposals.outcome_entity_type`
            is set to when this creator runs. Defaults to `entity_type`.

    Usage:
        @register("job", schema=JobProposalPayload)
        async def create_job(payload, org_id, actor, db):
            ...
    """
    def decorator(fn: CreatorFn) -> CreatorFn:
        if entity_type in _REGISTRY:
            logger.warning(
                "Overwriting registered creator for entity_type=%r "
                "(previously %s, now %s) — check for duplicate imports",
                entity_type, _REGISTRY[entity_type].creator, fn,
            )
        _REGISTRY[entity_type] = _RegistryEntry(
            creator=fn,
            schema=schema,
            outcome_entity_type=outcome_entity_type or entity_type,
        )
        return fn
    return decorator


def get_entry(entity_type: str) -> _RegistryEntry:
    """Return the registry entry for `entity_type`. Raises `KeyError`
    with a clear message if the caller tried to use an unknown type —
    that's a programmer error (e.g., typo), not a runtime condition."""
    if entity_type not in _REGISTRY:
        raise KeyError(
            f"No proposal creator registered for entity_type={entity_type!r}. "
            f"Known types: {sorted(_REGISTRY.keys())}. "
            "Add a creator under src/services/proposals/creators/ and import it "
            "from src/services/proposals/creators/__init__.py."
        )
    return _REGISTRY[entity_type]


def known_entity_types() -> list[str]:
    """For test + admin introspection."""
    return sorted(_REGISTRY.keys())
