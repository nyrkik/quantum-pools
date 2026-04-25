"""Inbox rules CRUD — unified sender/recipient routing + tagging.

Replaces the older split between `inbox_routing_rules` (under
`/inbox-routing-rules`) and the implicit `suppressed_email_senders`
endpoints. This one router is the sole write path. The old router is
kept for read-only backward compat until Phase D of the unification plan.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import OrgUserContext, require_roles
from src.core.database import get_db
from src.models.inbox_rule import InboxRule
from src.models.organization_user import OrgRole
from src.services.inbox_rules_service import (
    ALL_ACTION_TYPES,
    ALL_CONDITION_FIELDS,
)

router = APIRouter(prefix="/inbox-rules", tags=["inbox-rules"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


_OPERATORS = Literal[
    "equals", "contains", "starts_with", "ends_with", "matches"
]


class Condition(BaseModel):
    field: str
    operator: _OPERATORS
    # Scalar string OR a list of strings. A list matches when ANY element
    # satisfies the operator — lets a single rule collapse what previously
    # required N parallel rules (e.g., one "sender contains [mailchimp,
    # sendgrid, hubspot, ...]" rule instead of one per domain).
    value: str | list[str]


class Action(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)




def _validate_rule_body(conditions: list[Condition], actions: list[Action]) -> None:
    """Fail closed on unknown fields or action types."""
    for c in conditions:
        if c.field not in ALL_CONDITION_FIELDS:
            raise HTTPException(
                400, f"Unknown condition field '{c.field}'. "
                     f"Allowed: {sorted(ALL_CONDITION_FIELDS)}"
            )
    for a in actions:
        if a.type not in ALL_ACTION_TYPES:
            raise HTTPException(
                400, f"Unknown action type '{a.type}'. "
                     f"Allowed: {sorted(ALL_ACTION_TYPES)}"
            )
    if not actions:
        raise HTTPException(400, "Rule must have at least one action")


class RuleCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    # Priority is no longer exposed in the UI — a new rule appends to the end
    # by default. Callers can still pin an explicit priority if they need to.
    priority: int | None = None
    conditions: list[Condition] = Field(default_factory=list)
    actions: list[Action]
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    priority: int | None = None
    conditions: list[Condition] | None = None
    actions: list[Action] | None = None
    is_active: bool | None = None


class RuleReorder(BaseModel):
    """Flat list of rule ids in the order the user wants them evaluated."""
    rule_ids: list[str]


class RuleResponse(BaseModel):
    id: str
    name: str | None
    priority: int
    conditions: list[dict]
    actions: list[dict]
    is_active: bool
    created_by: str | None
    created_at: str


def _to_response(rule: InboxRule) -> RuleResponse:
    return RuleResponse(
        id=rule.id,
        name=rule.name,
        priority=rule.priority,
        conditions=list(rule.conditions or []),
        actions=list(rule.actions or []),
        is_active=rule.is_active,
        created_by=rule.created_by,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class MatchPreviewResponse(BaseModel):
    state: Literal["covered", "promotable", "unclear"]
    rule_id: str | None = None
    rule_name: str | None = None
    append_value: str | None = None


@router.get("/match-preview")
async def match_preview(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> MatchPreviewResponse:
    """For the auto-handled banner: does an existing active rule already
    cover this sender, or is there a clean rule to append the sender to?

    Backs the three-state banner (covered / promotable / unclear) — see
    ``InboxRulesService.preview_append_match`` for the semantics.
    """
    from src.models.agent_thread import AgentThread
    from src.models.inbox_folder import InboxFolder
    from src.services.inbox_rules_service import InboxRulesService

    thread = (await db.execute(
        select(AgentThread).where(
            AgentThread.id == thread_id,
            AgentThread.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    spam_folder_id = (await db.execute(
        select(InboxFolder.id).where(
            InboxFolder.organization_id == ctx.organization_id,
            InboxFolder.system_key == "spam",
        )
    )).scalar_one_or_none()

    result = await InboxRulesService(db).preview_append_match(
        ctx.organization_id,
        thread.contact_email or "",
        thread.folder_id,
        spam_folder_id,
    )
    return MatchPreviewResponse(**result)


class AppendSenderBody(BaseModel):
    value: str


@router.post("/{rule_id}/append-sender")
async def append_sender(
    rule_id: str,
    body: AppendSenderBody,
    thread_id: str | None = None,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Append a sender value to an existing rule's sender-based condition.

    Called from the auto-handled banner's "Add to rule" button. Also fires
    the AgentLearningService acceptance signal for the thread so the
    classifier stays in sync with the user's deterministic choice.
    """
    from src.services.inbox_rules_service import InboxRulesService

    try:
        result = await InboxRulesService(db).append_sender_to_rule(
            ctx.organization_id, rule_id, body.value,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Best-effort: fire the learning-acceptance signal so the classifier
    # also learns from the human-confirmed outcome.
    if thread_id:
        try:
            from src.models.agent_message import AgentMessage
            from src.services.agents.agent_learning_service import AgentLearningService
            from sqlalchemy import desc

            msg = (await db.execute(
                select(AgentMessage).where(
                    AgentMessage.thread_id == thread_id,
                    AgentMessage.organization_id == ctx.organization_id,
                    AgentMessage.direction == "inbound",
                ).order_by(desc(AgentMessage.received_at)).limit(1)
            )).scalar_one_or_none()
            if msg:
                learner = AgentLearningService(db)
                await learner.record_correction(
                    organization_id=ctx.organization_id,
                    agent_type="email_classifier",
                    category=msg.category or "general",
                    customer_id=msg.matched_customer_id,
                    input_context=f"Subject: {msg.subject}\n\nBody: {(msg.body or '')[:500]}",
                    original_output=f"category={msg.category}, status={msg.status}",
                    corrected_output=None,
                    correction_type="acceptance",
                    correction_note=f"User promoted to rule {rule_id}",
                    reviewed_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip() or ctx.user.email,
                )
        except Exception:
            pass  # never block the promotion on a learning-signal failure

    return result


class CoverageCheckBody(BaseModel):
    conditions: list[Condition]
    actions: list[Action]
    exclude_id: str | None = None


@router.post("/check-coverage")
async def check_coverage(
    body: CoverageCheckBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Pre-save check: is this rule already covered by an existing one?

    Returns ``{covered_by: {...}}`` when an existing active rule already
    matches every sender value the new rule targets AND shares at least
    one action type. Drives the editor's "X already covers this" warning.
    """
    from src.services.inbox_rules_service import InboxRulesService

    result = await InboxRulesService(db).check_coverage(
        ctx.organization_id,
        [c.model_dump() for c in body.conditions],
        [a.model_dump() for a in body.actions],
        exclude_id=body.exclude_id,
    )
    return {"covered_by": result}


class ApplyToExistingBody(BaseModel):
    dry_run: bool = False


@router.post("/{rule_id}/apply-to-existing")
async def apply_rule_to_existing(
    rule_id: str,
    body: ApplyToExistingBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Back-apply a rule to existing threads.

    `dry_run=true` returns the match count + sample so the UI can preview
    "this will affect N threads" before the user confirms; `dry_run=false`
    performs the apply + commits.
    """
    from src.services.inbox_rules_service import InboxRulesService

    return await InboxRulesService(db).apply_to_existing_threads(
        rule_id, ctx.organization_id, dry_run=body.dry_run,
    )


@router.get("")
async def list_rules(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List every rule for the org, priority-ASC then created-ASC."""
    rows = (await db.execute(
        select(InboxRule)
        .where(InboxRule.organization_id == ctx.organization_id)
        .order_by(InboxRule.priority.asc(), InboxRule.created_at.asc())
    )).scalars().all()
    return [_to_response(r) for r in rows]


@router.post("", status_code=201)
async def create_rule(
    body: RuleCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    _validate_rule_body(body.conditions, body.actions)

    # Default: append to the end. Pull the current max priority and add 10 so
    # there's room for the user to drag a new rule above an existing one
    # without re-numbering everything.
    if body.priority is None:
        max_priority = (
            await db.execute(
                select(InboxRule.priority)
                .where(InboxRule.organization_id == ctx.organization_id)
                .order_by(InboxRule.priority.desc())
                .limit(1)
            )
        ).scalar()
        priority = (max_priority or 0) + 10
    else:
        priority = body.priority

    rule = InboxRule(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        name=body.name,
        priority=priority,
        conditions=[c.model_dump() for c in body.conditions],
        actions=[a.model_dump() for a in body.actions],
        is_active=body.is_active,
        created_by=(
            f"{ctx.user.first_name} {ctx.user.last_name}".strip() or ctx.user.email
        ),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@router.post("/reorder")
async def reorder_rules(
    body: RuleReorder,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Write priorities to match the supplied order.

    Rules not in `rule_ids` are left untouched (but will end up AFTER the
    reordered set, since we renumber starting at 10 in steps of 10 and
    the maximum reordered priority is `10 * N`).
    """
    if not body.rule_ids:
        return {"updated": 0}

    rows = (await db.execute(
        select(InboxRule).where(
            InboxRule.organization_id == ctx.organization_id,
            InboxRule.id.in_(body.rule_ids),
        )
    )).scalars().all()
    by_id = {r.id: r for r in rows}

    updated = 0
    for index, rule_id in enumerate(body.rule_ids):
        rule = by_id.get(rule_id)
        if rule is None:
            # Unknown id — ignore rather than failing the whole reorder.
            continue
        new_priority = (index + 1) * 10
        if rule.priority != new_priority:
            rule.priority = new_priority
            updated += 1
    await db.commit()
    return {"updated": updated}


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    rule = (await db.execute(
        select(InboxRule).where(
            InboxRule.id == rule_id,
            InboxRule.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    if body.conditions is not None or body.actions is not None:
        new_conditions = body.conditions if body.conditions is not None else [
            Condition(**c) for c in (rule.conditions or [])
        ]
        new_actions = body.actions if body.actions is not None else [
            Action(**a) for a in (rule.actions or [])
        ]
        _validate_rule_body(new_conditions, new_actions)
        rule.conditions = [c.model_dump() for c in new_conditions]
        rule.actions = [a.model_dump() for a in new_actions]

    if body.name is not None:
        rule.name = body.name
    if body.priority is not None:
        rule.priority = body.priority
    if body.is_active is not None:
        rule.is_active = body.is_active

    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    rule = (await db.execute(
        select(InboxRule).where(
            InboxRule.id == rule_id,
            InboxRule.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"deleted": True}
