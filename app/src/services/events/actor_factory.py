"""Actor construction helpers — centralized so every emit site builds
the right Actor for the situation.

Design reference: docs/ai-platform-phase-1.md §5.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.events.platform_event_service import Actor

if TYPE_CHECKING:
    from src.api.deps import OrgUserContext


def actor_from_org_ctx(ctx: "OrgUserContext") -> Actor:
    """Build a user-actor from the standard FastAPI request context.

    Populates user_id + acting_as_user_id + view_as_role when present,
    so events correctly distinguish "who logged in" from "who they're
    viewing-as" (dev mode / future support impersonation).
    """
    return Actor(
        actor_type="user",
        user_id=ctx.user.id,
        # view_as_role / acting_as_user_id propagation comes when the
        # middleware exposes them. Not in Step 4 scope.
    )


def actor_system() -> Actor:
    """System-originated event (cron job, webhook, background sweep)."""
    return Actor(actor_type="system")


def actor_agent(agent_type: str) -> Actor:
    """AI agent output event. `agent_type` should match AgentLearningService
    conventions (e.g., 'email_classifier', 'email_drafter')."""
    return Actor(actor_type="agent", actor_agent_type=agent_type)
