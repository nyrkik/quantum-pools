"""Proposal creator: `workflow_config` entity_type.

Phase 6 entity. The `workflow_observer` agent stages proposals targeting
the JSONB columns on `org_workflow_config` — `post_creation_handlers` or
`default_assignee_strategy` — that the existing scalar `org_config`
creator can't represent (it's whitelisted single-key scalars per its
own docstring).

Payload is patch-shaped (`{target, op, value}`) rather than full-replace
so a meta-proposal can change one field without restating the whole
config. The creator reads current state, applies the patch, and writes
through `WorkflowConfigService.put` so handler-name validation and the
`workflow_config.changed` event emit happen via the canonical path.

Op semantics:
- `set`: replace the target field with `value`.
- `merge`: shallow-merge `value` into the target field (keys not in
  `value` survive).

ALLOWED_TARGETS is the explicit whitelist — never accept arbitrary
attribute names from the proposal payload.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register
from src.services.workflow.config_service import WorkflowConfigService


ALLOWED_TARGETS = {"post_creation_handlers", "default_assignee_strategy"}


class WorkflowConfigProposalPayload(BaseModel):
    target: Literal["post_creation_handlers", "default_assignee_strategy"]
    op: Literal["set", "merge"]
    value: Any  # type validated downstream by WorkflowConfigService.put


@register("workflow_config", schema=WorkflowConfigProposalPayload)
async def create_workflow_config_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    svc = WorkflowConfigService(db)
    current = await svc.get_or_default(org_id)

    target = payload["target"]
    op = payload["op"]
    value = payload["value"]

    if op == "set":
        new_value = value
    else:
        # merge — only meaningful for dict-shaped targets, which both
        # current ALLOWED_TARGETS happen to be.
        if not isinstance(value, dict) or not isinstance(current[target], dict):
            raise ValueError(
                f"merge op requires both current and incoming values to be dicts "
                f"(target={target!r})"
            )
        new_value = {**current[target], **value}

    # Build the full put() payload — patch the target field, leave the
    # other untouched. put() validates handler names + emits
    # workflow_config.changed.
    put_kwargs = {
        "post_creation_handlers": current["post_creation_handlers"],
        "default_assignee_strategy": current["default_assignee_strategy"],
    }
    put_kwargs[target] = new_value

    await svc.put(
        org_id=org_id,
        actor=actor,
        **put_kwargs,
    )

    # ProposalService.accept reads .id from the return value to populate
    # outcome_entity_id. The OrgWorkflowConfig row is keyed by org_id,
    # so we return a stand-in with that id.
    return _WorkflowConfigResult(id=org_id, target=target, op=op, applied_value=new_value)


class _WorkflowConfigResult:
    """Lightweight return shape — ProposalService reads .id."""
    __slots__ = ("id", "target", "op", "applied_value")

    def __init__(self, id: str, target: str, op: str, applied_value: Any):
        self.id = id
        self.target = target
        self.op = op
        self.applied_value = applied_value
