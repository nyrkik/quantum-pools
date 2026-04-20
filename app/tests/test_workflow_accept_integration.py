"""Phase 4 Step 5 — end-to-end accept-to-next-step integration test.

Closes the loop: stage a `job` proposal the normal way → accept it
via ProposalService.accept → run WorkflowConfigService.resolve_next_step
exactly as the /proposals/{id}/accept router does → assert the UI
gets a real NextStep back.

Routes through the real services (no mocks), so a future regression
in the creator ↔ handler contract (e.g. the job creator starts
returning something other than an AgentAction) is caught here.
"""

from __future__ import annotations

import uuid

import pytest

from src.models.org_workflow_config import OrgWorkflowConfig
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.proposals import ProposalService
from src.services.workflow.config_service import WorkflowConfigService


async def _seed_user(db, org_id: str, first_name: str = "Kim") -> str:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"wfi-{uid[:8]}@t.com",
        hashed_password="x", first_name=first_name, last_name="User",
        is_active=True,
    ))
    db.add(OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_id, user_id=uid, role=OrgRole.owner,
    ))
    await db.flush()
    return uid


async def _stage_job(db, org_id: str) -> str:
    """Stage a minimal job proposal via the real ProposalService."""
    p = await ProposalService(db).stage(
        org_id=org_id,
        agent_type="test_integration",
        entity_type="job",
        source_type="agent_thread",
        source_id=str(uuid.uuid4()),
        proposed_payload={
            "action_type": "service",
            "description": "Check pump filter",
        },
    )
    return p.id


@pytest.mark.asyncio
async def test_accept_job_proposal_returns_assign_inline_by_default(
    db_session, org_a,
):
    """System defaults: {'job': 'assign_inline'}. Accepting a job
    proposal should return a next_step with that kind, and the initial
    payload should carry the newly-created job's id."""
    uid = await _seed_user(db_session, org_a.id)
    proposal_id = await _stage_job(db_session, org_a.id)
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=uid)
    proposal, created = await ProposalService(db_session).accept(
        proposal_id=proposal_id, actor=actor,
    )

    next_step = await WorkflowConfigService(db_session).resolve_next_step(
        proposal=proposal, created=created, org_id=org_a.id, actor=actor,
    )
    await db_session.commit()

    assert next_step is not None
    assert next_step["kind"] == "assign_inline"
    assert next_step["initial"]["entity_type"] == "job"
    assert next_step["initial"]["entity_id"] == created.id
    # The seeded user shows up in the assignee picker.
    option_ids = [o["id"] for o in next_step["initial"]["assignee_options"]]
    assert uid in option_ids


@pytest.mark.asyncio
async def test_accept_job_proposal_respects_org_config_override(
    db_session, org_a,
):
    """When the org overrides the job handler to unassigned_pool, that
    handler wins over the system default."""
    uid = await _seed_user(db_session, org_a.id)
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "unassigned_pool"},
        default_assignee_strategy={"strategy": "always_ask"},
    ))
    proposal_id = await _stage_job(db_session, org_a.id)
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=uid)
    proposal, created = await ProposalService(db_session).accept(
        proposal_id=proposal_id, actor=actor,
    )
    next_step = await WorkflowConfigService(db_session).resolve_next_step(
        proposal=proposal, created=created, org_id=org_a.id, actor=actor,
    )
    await db_session.commit()

    assert next_step["kind"] == "unassigned_pool"
    assert next_step["initial"]["entity_id"] == created.id
    # pool_count is an int. Freshly-created job is unassigned + open so
    # it counts itself; other orgs don't leak in.
    assert isinstance(next_step["initial"]["pool_count"], int)
    assert next_step["initial"]["pool_count"] >= 1


@pytest.mark.asyncio
async def test_accept_returns_next_step_null_for_unmapped_entity_type(
    db_session, org_a,
):
    """No handler configured for case_link under system defaults →
    resolve_next_step returns None. The accept still succeeds; the
    frontend just gets null and moves on."""
    uid = await _seed_user(db_session, org_a.id)
    # Seed a minimal thread + case so the case_link creator has real FKs
    # to wire up.
    from src.models.agent_thread import AgentThread
    from src.models.service_case import ServiceCase

    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        thread_key=f"t-{uuid.uuid4().hex[:8]}",
        contact_email="x@example.com",
        subject="Test",
        status="pending",
        category="general",
        message_count=1,
        last_direction="inbound",
    )
    case = ServiceCase(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        case_number=f"SC-WF-{uuid.uuid4().hex[:6]}",
        title="target",
        status="new",
        source="test",
    )
    db_session.add_all([thread, case])
    await db_session.flush()

    p = await ProposalService(db_session).stage(
        org_id=org_a.id,
        agent_type="test_integration",
        entity_type="case_link",
        source_type="agent_thread",
        source_id=thread.id,
        proposed_payload={
            "entity_type": "thread",
            "entity_id": thread.id,
            "case_id": case.id,
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=uid)
    proposal, created = await ProposalService(db_session).accept(
        proposal_id=p.id, actor=actor,
    )
    next_step = await WorkflowConfigService(db_session).resolve_next_step(
        proposal=proposal, created=created, org_id=org_a.id, actor=actor,
    )
    await db_session.commit()

    # case_link isn't mapped in SYSTEM_DEFAULTS — next_step is null.
    assert next_step is None
