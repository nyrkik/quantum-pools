"""Shared helpers for handlers that ask the user to pick an assignee.

The default-assignee strategy lives in `org_workflow_config.default_assignee_strategy`
and is consulted by both `assign_inline` and `schedule_inline`. Strategies:

- `last_used_in_org`: the assignee of the most recently assigned job in
  this org (any creator). Good proxy for "who's doing this work right
  now" at small-team scale without per-user tracking infra. Defaults
  to `fallback_user_id` when no prior assignments exist.
- `fixed`: the user_id stored in `fallback_user_id` always.
- `always_ask`: no default — the picker shows no pre-selection.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction
from src.models.organization_user import OrganizationUser
from src.models.user import User


async def load_assignee_options(
    org_id: str, db: AsyncSession,
) -> list[dict]:
    """Every org user as `{id, name, first_name}` for the picker.

    `first_name` is included because `AgentAction.assigned_to` stores
    the first name string, not a user_id — the frontend needs it to
    build the PUT /agent-actions/{id} payload after the user picks.
    Active users only.
    """
    rows = (await db.execute(
        select(User.id, User.first_name, User.last_name, OrganizationUser.role)
        .join(OrganizationUser, OrganizationUser.user_id == User.id)
        .where(
            OrganizationUser.organization_id == org_id,
            User.is_active == True,  # noqa: E712
        )
        .order_by(User.first_name)
    )).all()
    options = []
    for uid, fn, ln, role in rows:
        name = " ".join(filter(None, [fn, ln])).strip() or fn or "Unknown"
        label = f"{name} ({role.capitalize()})" if role else name
        options.append({
            "id": uid,
            "name": label,
            "first_name": fn or "Unknown",
        })
    return options


async def resolve_default_assignee(
    *,
    strategy: dict,
    org_id: str,
    actor_user_id: Optional[str],
    db: AsyncSession,
) -> Optional[str]:
    """Apply the org's default_assignee_strategy to pick a pre-selected
    user_id. Returns None when the strategy is `always_ask` or when a
    `last_used_in_org` lookup returns no match and no fallback is set.

    `actor_user_id` is accepted for future per-user strategies (Phase 4b);
    today's strategies don't consult it.
    """
    _ = actor_user_id
    kind = strategy.get("strategy", "last_used_in_org")
    fallback = strategy.get("fallback_user_id")

    if kind == "always_ask":
        return None
    if kind == "fixed":
        return fallback
    if kind == "last_used_in_org":
        # "Who was the assignee of the most recent job in this org?"
        # AgentAction.assigned_to is a first_name string (legacy), so
        # translate it back to a user_id via User.first_name + the org
        # membership table. Crude but accurate for small teams where
        # first names are unique; good enough until per-user tracking
        # is justified by dogfood data.
        row = (await db.execute(
            select(AgentAction.assigned_to)
            .where(
                AgentAction.organization_id == org_id,
                AgentAction.assigned_to.is_not(None),
            )
            .order_by(desc(AgentAction.created_at))
            .limit(1)
        )).first()
        if not (row and row[0]):
            return fallback
        last_name = row[0]
        # If the stored value already looks like a user_id (e.g., test
        # fixtures seed it that way), return it directly so the matching
        # path in the handler stays simple.
        if len(last_name) == 36 and last_name.count("-") == 4:
            return last_name
        # Translate first_name → user_id.
        uid_row = (await db.execute(
            select(User.id)
            .join(OrganizationUser, OrganizationUser.user_id == User.id)
            .where(
                OrganizationUser.organization_id == org_id,
                User.first_name == last_name,
                User.is_active == True,  # noqa: E712
            )
            .limit(1)
        )).first()
        if uid_row and uid_row[0]:
            return uid_row[0]
        return fallback

    # Unknown strategy → safe no-default fallback.
    return fallback
