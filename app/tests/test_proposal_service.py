"""Unit tests for ProposalService.

Contract from docs/ai-platform-phase-2.md §5. The creators here are
test-only stubs so we exercise the state machine + event + learning
path without depending on the real creators (which Step 3 adds).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from src.models.user import User
from src.models.agent_proposal import (
    STATUS_ACCEPTED,
    STATUS_EDITED,
    STATUS_EXPIRED,
    STATUS_REJECTED,
    STATUS_STAGED,
    STATUS_SUPERSEDED,
)
from src.services.events.platform_event_service import Actor
from src.services.proposals.proposal_service import (
    ProposalConflictError,
    ProposalService,
    ProposalStateError,
)
from src.services.proposals.registry import register


# --- Test fixtures: a lightweight registered entity_type -----------------

class _StubPayload(BaseModel):
    title: str
    customer_id: str | None = None


class _StubCreated:
    def __init__(self, title: str):
        self.id = f"stub-{uuid.uuid4().hex[:8]}"
        self.title = title


@register("test_stub", schema=_StubPayload, outcome_entity_type="stub_entity")
async def _stub_creator(payload: dict, org_id: str, actor: Actor, db) -> Any:
    return _StubCreated(title=payload["title"])


@register("test_stub_conflict")  # no schema — testing conflict path
async def _conflict_creator(payload: dict, org_id: str, actor: Actor, db) -> Any:
    raise ProposalConflictError("already exists")


@register("test_stub_unvalidated")  # no schema, no conflict
async def _passthrough_creator(payload: dict, org_id: str, actor: Actor, db) -> Any:
    return {"id": "passthrough-1", **payload}


# --- Tests ---------------------------------------------------------------


async def _seed_user(db) -> str:
    """agent_proposals.resolved_by_user_id has a FK to users. Tests that
    call accept/edit/reject as a user actor must seed a real row."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"pt-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="Proposal", last_name="Tester",
    )
    db.add(user)
    await db.flush()
    return user.id


@pytest.mark.asyncio
async def test_stage_happy_path(db_session, org_a, event_recorder):
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="email_drafter",
        entity_type="test_stub",
        source_type="test",
        source_id="src-1",
        proposed_payload={"title": "Replace pump", "customer_id": "c-1"},
        confidence=0.9,
    )
    await db_session.commit()

    assert p.status == STATUS_STAGED
    assert p.proposed_payload == {"title": "Replace pump", "customer_id": "c-1"}
    assert p.confidence == 0.9

    await event_recorder.assert_emitted("proposal.staged", agent_proposal_id=p.id)


@pytest.mark.asyncio
async def test_stage_unknown_entity_type_raises(db_session, org_a):
    service = ProposalService(db_session)
    with pytest.raises(KeyError):
        await service.stage(
            org_id=org_a.id, agent_type="x", entity_type="not_a_thing",
            source_type="t", source_id=None, proposed_payload={},
        )


@pytest.mark.asyncio
async def test_stage_invalid_payload_raises(db_session, org_a):
    """Schema-validated entity_types reject malformed payloads at stage
    time (not accept time)."""
    service = ProposalService(db_session)
    with pytest.raises(Exception):  # pydantic.ValidationError
        await service.stage(
            org_id=org_a.id, agent_type="x", entity_type="test_stub",
            source_type="t", source_id=None,
            proposed_payload={"missing_title": True},  # no 'title' field
        )


@pytest.mark.asyncio
async def test_accept_runs_creator_and_marks_accepted(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="email_drafter", entity_type="test_stub",
        source_type="t", source_id=None,
        proposed_payload={"title": "Original"},
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, created = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == STATUS_ACCEPTED
    assert p_resolved.outcome_entity_type == "stub_entity"
    assert p_resolved.outcome_entity_id == created.id
    assert p_resolved.resolved_by_user_id == user_id
    assert created.title == "Original"
    await event_recorder.assert_emitted("proposal.accepted", agent_proposal_id=p.id)


@pytest.mark.asyncio
async def test_edit_and_accept_computes_json_patch(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="email_drafter", entity_type="test_stub",
        source_type="t", source_id=None,
        proposed_payload={"title": "Original", "customer_id": "c-1"},
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, created = await service.edit_and_accept(
        proposal_id=p.id, actor=actor,
        edited_payload={"title": "Edited", "customer_id": "c-1"},
    )
    await db_session.commit()

    assert p_resolved.status == STATUS_EDITED
    assert created.title == "Edited"
    assert p_resolved.user_delta is not None
    # The patch must describe ONLY the title change.
    ops = p_resolved.user_delta
    assert any(op["path"] == "/title" and op["value"] == "Edited" for op in ops)
    assert not any(op["path"] == "/customer_id" for op in ops)

    await event_recorder.assert_emitted("proposal.edited", agent_proposal_id=p.id)


@pytest.mark.asyncio
async def test_reject_permanently_flags_record(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="email_drafter", entity_type="test_stub",
        source_type="t", source_id=None,
        proposed_payload={"title": "X"},
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved = await service.reject(
        proposal_id=p.id, actor=actor,
        permanently=True, note="Wrong pattern",
    )
    await db_session.commit()

    assert p_resolved.status == STATUS_REJECTED
    assert p_resolved.rejected_permanently is True
    assert p_resolved.resolution_note == "Wrong pattern"

    # Permanent-reject fires a distinct event type.
    await event_recorder.assert_emitted(
        "proposal.rejected_permanently", agent_proposal_id=p.id
    )


@pytest.mark.asyncio
async def test_reject_non_permanent_emits_plain_rejected(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="email_drafter", entity_type="test_stub",
        source_type="t", source_id=None,
        proposed_payload={"title": "X"},
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    await service.reject(proposal_id=p.id, actor=actor)
    await db_session.commit()

    await event_recorder.assert_emitted("proposal.rejected", agent_proposal_id=p.id)
    await event_recorder.assert_not_emitted(
        "proposal.rejected_permanently", agent_proposal_id=p.id
    )


@pytest.mark.asyncio
async def test_accept_on_already_resolved_raises(db_session, org_a):
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="x", entity_type="test_stub",
        source_type="t", source_id=None,
        proposed_payload={"title": "X"},
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    # Second accept attempt → ProposalStateError
    with pytest.raises(ProposalStateError):
        await service.accept(proposal_id=p.id, actor=actor)


@pytest.mark.asyncio
async def test_accept_conflict_soft_rejects(db_session, org_a, event_recorder):
    """Creator raises ProposalConflictError → proposal marked rejected
    with reason=user_created_already, not hard-raised."""
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id, agent_type="x", entity_type="test_stub_conflict",
        source_type="t", source_id=None, proposed_payload={"any": "thing"},
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, created = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == STATUS_REJECTED
    assert p_resolved.resolution_note == "superseded_by_user_action"
    assert created is None

    await event_recorder.assert_emitted("proposal.rejected", agent_proposal_id=p.id)


@pytest.mark.asyncio
async def test_supersede_chains_proposals(db_session, org_a, event_recorder):
    service = ProposalService(db_session)
    old = await service.stage(
        org_id=org_a.id, agent_type="x", entity_type="test_stub",
        source_type="t", source_id="s-1", proposed_payload={"title": "v1"},
    )
    await db_session.commit()

    new = await service.supersede(
        old_proposal_id=old.id,
        new_payload={"title": "v2"},
        new_confidence=0.95,
    )
    await db_session.commit()

    # Old is superseded + linked.
    await db_session.refresh(old)
    assert old.status == STATUS_SUPERSEDED
    assert old.superseded_by_id == new.id

    # New is fresh staged, inherits source + agent + entity.
    assert new.status == STATUS_STAGED
    assert new.source_id == "s-1"
    assert new.agent_type == "x"
    assert new.confidence == 0.95

    await event_recorder.assert_emitted("proposal.superseded", agent_proposal_id=old.id)


@pytest.mark.asyncio
async def test_expire_stale_processes_old_staged_only(db_session, org_a, event_recorder):
    """Only staged proposals older than age_days get expired. Accepted /
    rejected proposals are left alone; fresh staged ones too."""
    service = ProposalService(db_session)

    # Old staged (will expire)
    old_staged = await service.stage(
        org_id=org_a.id, agent_type="x", entity_type="test_stub",
        source_type="t", source_id=None, proposed_payload={"title": "stale"},
    )
    # Fresh staged (won't expire)
    fresh = await service.stage(
        org_id=org_a.id, agent_type="x", entity_type="test_stub",
        source_type="t", source_id=None, proposed_payload={"title": "fresh"},
    )
    # Accepted old (won't expire — not staged anymore)
    old_accepted = await service.stage(
        org_id=org_a.id, agent_type="x", entity_type="test_stub",
        source_type="t", source_id=None, proposed_payload={"title": "done"},
    )
    user_id = await _seed_user(db_session)
    await service.accept(
        proposal_id=old_accepted.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    # Age only the old_staged proposal
    await db_session.execute(
        text("UPDATE agent_proposals SET created_at = NOW() - interval '60 days' WHERE id = :id"),
        {"id": old_staged.id},
    )
    await db_session.commit()

    n = await service.expire_stale(age_days=30)
    await db_session.commit()
    assert n == 1

    await db_session.refresh(old_staged)
    await db_session.refresh(fresh)
    await db_session.refresh(old_accepted)

    assert old_staged.status == STATUS_EXPIRED
    assert fresh.status == STATUS_STAGED
    assert old_accepted.status == STATUS_ACCEPTED

    await event_recorder.assert_emitted("proposal.expired", agent_proposal_id=old_staged.id)


@pytest.mark.asyncio
async def test_known_entity_types_includes_stubs():
    """Smoke test that the registry is populated via the decorators at
    import time."""
    from src.services.proposals.registry import known_entity_types
    types = known_entity_types()
    assert "test_stub" in types
    assert "test_stub_conflict" in types
    assert "test_stub_unvalidated" in types
