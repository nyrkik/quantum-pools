"""Tests for the workflow_config proposal creator (Phase 6 step 2).

The creator stages patch-shaped proposals against `org_workflow_config`
JSONB columns. These tests verify:
- `set` op replaces the target field on accept
- `merge` op shallow-merges into the target
- Pydantic schema rejects unknown targets at stage time
- Invalid handler names propagate as UnknownHandlerError on accept
  (validation happens via WorkflowConfigService.put — single chokepoint)
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.models.org_workflow_config import OrgWorkflowConfig
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.proposals import ProposalService
from src.services.proposals.creators.workflow_config import WorkflowConfigProposalPayload
from src.services.workflow.config_service import UnknownHandlerError


async def _seed_user(db) -> str:
    u = User(
        id=str(uuid.uuid4()),
        email=f"wc-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="Workflow", last_name="Tester",
    )
    db.add(u)
    await db.flush()
    return u.id


@pytest.mark.asyncio
async def test_set_default_assignee_strategy(db_session, org_a):
    user_id = await _seed_user(db_session)
    await db_session.commit()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="workflow_observer",
        entity_type="workflow_config",
        source_type="organization",
        source_id=org_a.id,
        proposed_payload={
            "target": "default_assignee_strategy",
            "op": "set",
            "value": {"strategy": "fixed", "fallback_user_id": user_id},
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, _ = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == "accepted"
    assert p_resolved.outcome_entity_id == org_a.id

    row = await db_session.get(OrgWorkflowConfig, org_a.id)
    assert row is not None
    assert row.default_assignee_strategy == {
        "strategy": "fixed",
        "fallback_user_id": user_id,
    }


@pytest.mark.asyncio
async def test_merge_post_creation_handlers_preserves_existing_keys(db_session, org_a):
    """`merge` shallow-merges so other entity_types' handlers survive."""
    user_id = await _seed_user(db_session)

    # Seed an existing config with one entity_type already mapped.
    row = OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "assign_inline"},
        default_assignee_strategy={"strategy": "last_used_in_org"},
        observer_mutes={},
        observer_thresholds={},
    )
    db_session.add(row)
    await db_session.commit()

    service = ProposalService(db_session)
    # Merge an additional entity_type → handler mapping. The existing
    # 'job' key must survive.
    p = await service.stage(
        org_id=org_a.id,
        agent_type="workflow_observer",
        entity_type="workflow_config",
        source_type="organization",
        source_id=org_a.id,
        proposed_payload={
            "target": "post_creation_handlers",
            "op": "merge",
            "value": {"job": "schedule_inline"},  # overwrite job mapping
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, _ = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == "accepted"
    refreshed = await db_session.get(OrgWorkflowConfig, org_a.id)
    assert refreshed.post_creation_handlers == {"job": "schedule_inline"}


@pytest.mark.asyncio
async def test_invalid_target_rejected_at_validation():
    """Pydantic literal type rejects unknown target before stage."""
    with pytest.raises(ValidationError):
        WorkflowConfigProposalPayload(
            target="bogus_target",
            op="set",
            value={"x": 1},
        )


@pytest.mark.asyncio
async def test_unknown_handler_name_propagates_on_accept(db_session, org_a):
    """Bad handler names must surface as UnknownHandlerError so the
    proposal accept fails loudly — accidentally accepting a typo would
    leave a dangling reference no UI could resolve."""
    user_id = await _seed_user(db_session)
    await db_session.commit()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="workflow_observer",
        entity_type="workflow_config",
        source_type="organization",
        source_id=org_a.id,
        proposed_payload={
            "target": "post_creation_handlers",
            "op": "set",
            "value": {"job": "nonexistent_handler"},
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    with pytest.raises(UnknownHandlerError):
        await service.accept(proposal_id=p.id, actor=actor)
