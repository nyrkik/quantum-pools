"""Tests for the case_link proposal creator (Phase 3 Step 2).

Verifies the full chain: stage a case_link proposal → accept →
ServiceCaseService.set_entity_case runs → thread.case_id updated →
proposal marked accepted with outcome pointing at the case.
"""

from __future__ import annotations

import uuid

import pytest

from src.models.agent_thread import AgentThread
from src.models.service_case import ServiceCase
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.proposals import ProposalService


async def _seed_user(db) -> str:
    u = User(
        id=str(uuid.uuid4()),
        email=f"cl-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="Case", last_name="Linker",
    )
    db.add(u)
    await db.flush()
    return u.id


async def _seed_thread(db, org_id: str) -> str:
    t = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"test-{uuid.uuid4().hex[:8]}",
        contact_email="x@example.com",
        subject="Test",
        status="pending",
        category="general",
        message_count=1,
        last_direction="inbound",
    )
    db.add(t)
    await db.flush()
    return t.id


async def _seed_case(db, org_id: str) -> str:
    c = ServiceCase(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        case_number=f"SC-TEST-{uuid.uuid4().hex[:6]}",
        title="Link target",
        status="new",
        source="test",
    )
    db.add(c)
    await db.flush()
    return c.id


@pytest.mark.asyncio
async def test_case_link_accept_updates_thread(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    thread_id = await _seed_thread(db_session, org_a.id)
    case_id = await _seed_case(db_session, org_a.id)
    await db_session.commit()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="inbox_summarizer",
        entity_type="case_link",
        source_type="agent_thread",
        source_id=thread_id,
        proposed_payload={
            "entity_type": "thread",
            "entity_id": thread_id,
            "case_id": case_id,
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, result = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    # Proposal resolved with case id stamped as outcome
    assert p_resolved.status == "accepted"
    assert p_resolved.outcome_entity_type == "service_case"
    assert p_resolved.outcome_entity_id == case_id

    # Thread is now linked to the case
    await db_session.refresh(
        await db_session.get(AgentThread, thread_id)
    )
    t = await db_session.get(AgentThread, thread_id)
    assert t.case_id == case_id

    # proposal.accepted event fired
    await event_recorder.assert_emitted("proposal.accepted", agent_proposal_id=p.id)


@pytest.mark.asyncio
async def test_case_link_idempotent_on_already_linked(db_session, org_a):
    """Re-accepting a case_link proposal for a thread already linked to
    the target case must not fail — the set_entity_case transition is a
    no-op. Critical for the supersede path."""
    user_id = await _seed_user(db_session)
    thread_id = await _seed_thread(db_session, org_a.id)
    case_id = await _seed_case(db_session, org_a.id)

    # Pre-link the thread manually
    t = await db_session.get(AgentThread, thread_id)
    t.case_id = case_id
    await db_session.commit()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="inbox_summarizer",
        entity_type="case_link", source_type="agent_thread",
        source_id=thread_id,
        proposed_payload={
            "entity_type": "thread", "entity_id": thread_id, "case_id": case_id,
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, result = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == "accepted"
    # Thread still linked to same case (idempotent).
    t = await db_session.get(AgentThread, thread_id)
    assert t.case_id == case_id


@pytest.mark.asyncio
async def test_case_link_invalid_entity_type_rejected_at_stage(db_session, org_a):
    """ServiceCaseService only knows a fixed set of linkable entity
    types (LINKABLE_MODELS). An unknown one should fail at accept
    time with ValueError propagating through the creator."""
    user_id = await _seed_user(db_session)
    thread_id = await _seed_thread(db_session, org_a.id)
    case_id = await _seed_case(db_session, org_a.id)
    await db_session.commit()

    service = ProposalService(db_session)
    # Stage with a bogus inner entity_type — schema accepts arbitrary
    # strings so this surfaces at accept time (same class of error as
    # any creator raising).
    p = await service.stage(
        org_id=org_a.id, agent_type="inbox_summarizer",
        entity_type="case_link", source_type="agent_thread",
        source_id=thread_id,
        proposed_payload={
            "entity_type": "not_a_linkable_thing",
            "entity_id": thread_id,
            "case_id": case_id,
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    with pytest.raises(ValueError):
        await service.accept(proposal_id=p.id, actor=actor)
    await db_session.rollback()

    # Proposal stays staged (creator failure → rollback).
    p_after = await db_session.get(type(p), p.id)
    assert p_after.status == "staged"
