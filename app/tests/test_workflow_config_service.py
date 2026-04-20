"""Tests for WorkflowConfigService (Phase 4 Step 3).

Covers:
- get_or_default returns system defaults when no row exists
- put creates a row, put again updates in place
- put validates handler names (unknown → UnknownHandlerError)
- put validates entity_type compatibility (handler doesn't support → raise)
- resolve_next_step dispatches to the right handler based on config
- resolve_next_step returns None when no handler configured for entity_type
- resolve_next_step swallows handler exceptions (accept must not rollback)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from src.models.agent_action import AgentAction
from src.models.agent_proposal import AgentProposal
from src.models.org_workflow_config import OrgWorkflowConfig
from src.models.organization_user import OrganizationUser
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.workflow.config_service import (
    SYSTEM_DEFAULTS,
    UnknownHandlerError,
    WorkflowConfigService,
)


async def _seed_user_and_link(db, org_id: str) -> str:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"wfc-{uid[:8]}@t.com",
        hashed_password="x", first_name="Test", last_name="User",
        is_active=True,
    ))
    db.add(OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_id, user_id=uid, role="admin",
    ))
    await db.flush()
    return uid


def _actor(uid: str) -> Actor:
    return Actor(actor_type="user", user_id=uid)


# ---------------------------------------------------------------------------
# get_or_default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_default_no_row_returns_system_defaults(db_session, org_a):
    svc = WorkflowConfigService(db_session)
    cfg = await svc.get_or_default(org_a.id)
    assert cfg == SYSTEM_DEFAULTS
    # And it's a deep copy, not the shared reference.
    cfg["post_creation_handlers"]["job"] = "something_else"
    assert SYSTEM_DEFAULTS["post_creation_handlers"]["job"] == "assign_inline"


@pytest.mark.asyncio
async def test_get_or_default_row_overrides_defaults(db_session, org_a):
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "unassigned_pool"},
        default_assignee_strategy={"strategy": "always_ask"},
    ))
    await db_session.commit()

    cfg = await WorkflowConfigService(db_session).get_or_default(org_a.id)
    assert cfg["post_creation_handlers"]["job"] == "unassigned_pool"
    assert cfg["default_assignee_strategy"] == {"strategy": "always_ask"}


# ---------------------------------------------------------------------------
# put
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_creates_row_and_emits(db_session, org_a, event_recorder):
    uid = await _seed_user_and_link(db_session, org_a.id)
    await db_session.commit()

    svc = WorkflowConfigService(db_session)
    after = await svc.put(
        org_id=org_a.id,
        post_creation_handlers={"job": "schedule_inline"},
        default_assignee_strategy={"strategy": "always_ask"},
        actor=_actor(uid),
    )
    await db_session.commit()

    assert after["post_creation_handlers"]["job"] == "schedule_inline"
    # Row persisted.
    row = await db_session.get(OrgWorkflowConfig, org_a.id)
    assert row is not None
    assert row.post_creation_handlers == {"job": "schedule_inline"}

    event = await event_recorder.assert_emitted("workflow_config.changed")
    assert event["organization_id"] == org_a.id
    assert event["payload"]["after"]["post_creation_handlers"]["job"] == "schedule_inline"


@pytest.mark.asyncio
async def test_put_updates_existing_row(db_session, org_a):
    uid = await _seed_user_and_link(db_session, org_a.id)
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "assign_inline"},
        default_assignee_strategy={"strategy": "last_used_in_org"},
    ))
    await db_session.commit()

    await WorkflowConfigService(db_session).put(
        org_id=org_a.id,
        post_creation_handlers={"job": "unassigned_pool"},
        default_assignee_strategy={"strategy": "always_ask"},
        actor=_actor(uid),
    )
    await db_session.commit()

    row = await db_session.get(OrgWorkflowConfig, org_a.id)
    assert row.post_creation_handlers == {"job": "unassigned_pool"}


@pytest.mark.asyncio
async def test_put_rejects_unknown_handler(db_session, org_a):
    uid = await _seed_user_and_link(db_session, org_a.id)
    await db_session.commit()

    with pytest.raises(UnknownHandlerError) as excinfo:
        await WorkflowConfigService(db_session).put(
            org_id=org_a.id,
            post_creation_handlers={"job": "imaginary_handler"},
            default_assignee_strategy={"strategy": "always_ask"},
            actor=_actor(uid),
        )
    assert "imaginary_handler" in str(excinfo.value)
    assert "assign_inline" in str(excinfo.value)  # lists known handlers


@pytest.mark.asyncio
async def test_put_rejects_entity_type_mismatch(db_session, org_a):
    """A handler that doesn't declare support for `estimate` can't be
    bound to it."""
    uid = await _seed_user_and_link(db_session, org_a.id)
    await db_session.commit()

    with pytest.raises(UnknownHandlerError):
        await WorkflowConfigService(db_session).put(
            org_id=org_a.id,
            # assign_inline only supports "job"
            post_creation_handlers={"estimate": "assign_inline"},
            default_assignee_strategy={"strategy": "always_ask"},
            actor=_actor(uid),
        )


# ---------------------------------------------------------------------------
# resolve_next_step
# ---------------------------------------------------------------------------


async def _seed_proposal_and_action(db, org_id: str) -> tuple[AgentProposal, AgentAction]:
    action = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        action_type="service",
        description="Test job",
        status="open",
    )
    db.add(action)
    proposal = AgentProposal(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        agent_type="test_agent",
        entity_type="job",
        source_type="agent_thread",
        source_id=str(uuid.uuid4()),
        proposed_payload={},
        status="accepted",
        outcome_entity_type="agent_action",
        outcome_entity_id=action.id,
    )
    db.add(proposal)
    await db.flush()
    return proposal, action


@pytest.mark.asyncio
async def test_resolve_next_step_dispatches_to_configured_handler(db_session, org_a):
    uid = await _seed_user_and_link(db_session, org_a.id)
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "unassigned_pool"},
        default_assignee_strategy={"strategy": "always_ask"},
    ))
    proposal, action = await _seed_proposal_and_action(db_session, org_a.id)
    await db_session.commit()

    result = await WorkflowConfigService(db_session).resolve_next_step(
        proposal=proposal, created=action, org_id=org_a.id, actor=_actor(uid),
    )
    assert result is not None
    assert result["kind"] == "unassigned_pool"
    assert result["initial"]["entity_id"] == action.id


@pytest.mark.asyncio
async def test_resolve_next_step_falls_back_to_default_handler(db_session, org_a):
    """No row configured → system defaults say job → assign_inline."""
    uid = await _seed_user_and_link(db_session, org_a.id)
    proposal, action = await _seed_proposal_and_action(db_session, org_a.id)
    await db_session.commit()

    result = await WorkflowConfigService(db_session).resolve_next_step(
        proposal=proposal, created=action, org_id=org_a.id, actor=_actor(uid),
    )
    assert result is not None
    assert result["kind"] == "assign_inline"


@pytest.mark.asyncio
async def test_resolve_next_step_returns_none_for_unmapped_entity_type(db_session, org_a):
    """entity_type=estimate has no handler in system defaults → None."""
    uid = await _seed_user_and_link(db_session, org_a.id)
    proposal = AgentProposal(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        agent_type="test_agent",
        entity_type="estimate",  # no handler
        source_type="agent_thread",
        source_id=str(uuid.uuid4()),
        proposed_payload={},
        status="accepted",
        outcome_entity_type="invoice",
        outcome_entity_id=str(uuid.uuid4()),
    )
    db_session.add(proposal)
    await db_session.commit()

    result = await WorkflowConfigService(db_session).resolve_next_step(
        proposal=proposal, created=None, org_id=org_a.id, actor=_actor(uid),
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_next_step_swallows_handler_exceptions(db_session, org_a):
    """Handler failure must NOT surface to the caller — the accept
    response returns next_step=null instead of 500."""
    uid = await _seed_user_and_link(db_session, org_a.id)
    proposal, action = await _seed_proposal_and_action(db_session, org_a.id)
    await db_session.commit()

    async def boom(**kwargs):
        raise RuntimeError("handler blew up")

    with patch(
        "src.services.workflow.handlers.assign_inline.AssignInlineHandler.next_step_for",
        side_effect=boom,
    ):
        result = await WorkflowConfigService(db_session).resolve_next_step(
            proposal=proposal, created=action, org_id=org_a.id, actor=_actor(uid),
        )
    assert result is None
