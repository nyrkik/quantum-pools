"""Handler registry — one entry per handler name.

Concrete handlers self-register via the `@register` decorator at
import time. `WorkflowConfigService.resolve_next_step` (Step 3) looks
up the handler by name from the org's `post_creation_handlers` map
and dispatches to it.

Unknown handler name = KeyError so config-time mistakes surface loud.
The PUT /workflow/config endpoint validates names against this
registry before allowing a write, so runtime lookups shouldn't miss.
"""

from __future__ import annotations

import logging
from typing import Type

from src.services.workflow.types import WorkflowHandler

logger = logging.getLogger(__name__)

HANDLERS: dict[str, WorkflowHandler] = {}


def register(handler_cls: Type[WorkflowHandler]) -> Type[WorkflowHandler]:
    """Class-level decorator: instantiate + register by `name`.

    Each handler is stateless, so a single shared instance is fine.
    Overwriting an existing registration logs a warning — same pattern
    as `proposals/registry.py`.
    """
    instance = handler_cls()
    name = instance.name
    if name in HANDLERS:
        logger.warning(
            "Overwriting registered workflow handler %r (%s → %s)",
            name, HANDLERS[name].__class__, handler_cls,
        )
    HANDLERS[name] = instance
    return handler_cls


def get_handler(name: str) -> WorkflowHandler:
    """Look up a handler by name. Raises KeyError with the known names
    so misconfigurations surface with an actionable hint."""
    if name not in HANDLERS:
        raise KeyError(
            f"No workflow handler registered with name={name!r}. "
            f"Known handlers: {sorted(HANDLERS)}"
        )
    return HANDLERS[name]
