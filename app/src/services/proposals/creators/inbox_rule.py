"""Proposal creator: `inbox_rule` entity_type.

Phase 6 entity. The `workflow_observer` agent's
ClassificationOverrideDetector stages a proposal to create a new
inbox_rule when it sees the user repeatedly correcting category X → Y
for the same sender.

Validation chokepoint: `InboxRulesService.validate_rule_body` runs at
both stage time (via Pydantic model_validator below) and at accept time
(inside `create_rule`). Same logic, two safety nets — stage-time catches
malformed agent output before it sits in the DB; accept-time catches
edits the human made that drifted invalid.

The proposal card renders the rule in plain language via
`describe_rule()` below. Falls back to JSON for shapes the renderer
doesn't recognize.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor
from src.services.inbox_rules_service import (
    InboxRulesService,
    InvalidRuleError,
    validate_rule_body,
)
from src.services.proposals.registry import register


class InboxRuleProposalPayload(BaseModel):
    name: str | None = None
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_shape(self):
        # Stage-time validation. Re-runs at accept-time inside
        # InboxRulesService.create_rule — keeps drift impossible.
        try:
            validate_rule_body(self.conditions, self.actions)
        except InvalidRuleError as e:
            raise ValueError(str(e))
        return self


@register("inbox_rule", schema=InboxRuleProposalPayload)
async def create_inbox_rule_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    rule = await InboxRulesService(db).create_rule(
        org_id=org_id,
        conditions=payload["conditions"],
        actions=payload["actions"],
        name=payload.get("name"),
        is_active=payload.get("is_active", True),
        created_by=f"workflow_observer (accepted by user {actor.user_id})"
        if actor.user_id else "workflow_observer",
    )
    return rule


# ---------------------------------------------------------------------------
# Plain-language renderer
#
# The proposal card calls describe_rule() to show the user "what this rule
# will do" without exposing the JSONB. Falls back to JSON-ish text for
# shapes outside the common patterns the workflow_observer produces.
# ---------------------------------------------------------------------------

_FIELD_LABELS = {
    "sender_email": "sender",
    "sender_domain": "sender domain",
    "recipient_email": "recipient",
    "subject": "subject",
    "category": "category",
    "customer_id": "customer",
    "customer_matched": "matched-to-customer",
    "body": "body",
}

_OPERATOR_PHRASES = {
    "equals": "is",
    "contains": "contains",
    "starts_with": "starts with",
    "ends_with": "ends with",
    "matches": "matches pattern",
}

_ACTION_TEMPLATES = {
    "assign_folder": lambda p: f"move to folder \"{p.get('folder_key', '?')}\"",
    "assign_tag": lambda p: f"tag as \"{p.get('tag', '?')}\"",
    "assign_category": lambda p: f"set category to \"{p.get('category', '?')}\"",
    "set_visibility": lambda p: (
        "restrict visibility to roles "
        f"{p.get('role_slugs', '?')}"
    ),
    "suppress_contact_prompt": lambda p: "suppress new-contact prompt",
    "route_to_spam": lambda p: "route to spam",
    "mark_as_read": lambda p: "mark as read",
    "skip_customer_match": lambda p: "skip customer-match shortcut",
}


def _describe_value(value: Any) -> str:
    if isinstance(value, list):
        items = [str(v) for v in value]
        if len(items) <= 2:
            return " or ".join(f"\"{v}\"" for v in items)
        return f"\"{items[0]}\" or {len(items) - 1} more"
    return f"\"{value}\""


def describe_rule(payload: dict) -> str:
    """Plain-language one-liner for a proposed rule. Empty/unknown
    shapes degrade gracefully to a useful summary, never raise."""
    conditions = payload.get("conditions") or []
    actions = payload.get("actions") or []

    if not conditions and not actions:
        return "Empty rule"

    cond_phrases: list[str] = []
    for c in conditions:
        field = _FIELD_LABELS.get(c.get("field"), c.get("field") or "?")
        op = _OPERATOR_PHRASES.get(c.get("operator"), c.get("operator") or "?")
        val = _describe_value(c.get("value"))
        cond_phrases.append(f"{field} {op} {val}")

    action_phrases: list[str] = []
    for a in actions:
        tmpl = _ACTION_TEMPLATES.get(a.get("type"))
        if tmpl is None:
            action_phrases.append(f"{a.get('type', '?')}({a.get('params') or {}})")
        else:
            action_phrases.append(tmpl(a.get("params") or {}))

    when = " and ".join(cond_phrases) if cond_phrases else "every message"
    then = ", ".join(action_phrases) if action_phrases else "(no actions)"
    return f"When {when}: {then}"
