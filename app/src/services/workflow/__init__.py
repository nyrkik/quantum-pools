"""Workflow — post-creation handler system.

Phase 4 of the AI-platform build (see `docs/ai-platform-phase-4.md`).
When a proposal accepts and creates an entity, the workflow handler
for that org + entity_type tells the frontend "what happens next" —
typically an inline step like "pick an assignee" or "schedule it".

The handler abstraction is intentionally thin: each handler returns a
`NextStep(kind, initial)` describing the UI step, and the frontend's
component registry renders it. Handlers never mutate the created
entity directly — the frontend calls the canonical service endpoints
(e.g. `PUT /agent-actions/{id}`) to apply the user's input.

Import `handlers` at package-import time so every concrete handler
self-registers via the @register decorator.
"""

from src.services.workflow.registry import (  # noqa: F401
    HANDLERS,
    get_handler,
    register,
)
from src.services.workflow.types import (  # noqa: F401
    NextStep,
    WorkflowHandler,
)
from src.services.workflow import handlers  # noqa: F401
