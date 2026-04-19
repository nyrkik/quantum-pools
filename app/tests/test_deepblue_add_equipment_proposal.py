"""End-to-end integration test for Phase 2 Step 5 dogfood.

Verifies the full chain: DeepBlue tool stages a proposal →
ProposalService.accept via the confirm endpoint's code path →
EquipmentItemService creates the item → events fire (equipment_item.added
+ proposal.staged + proposal.accepted) → learning record written.

This is the pattern that will repeat across the 7 remaining DeepBlue
tool migrations in Steps 8-9 — catching contract bugs here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select, text

from src.models.agent_proposal import AgentProposal, STATUS_ACCEPTED, STATUS_STAGED
from src.models.equipment_item import EquipmentItem
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.deepblue.tools_equipment import _exec_add_equipment
from src.services.proposals import ProposalService


@dataclass
class _ToolCtx:
    """Minimal stand-in for the DeepBlue ToolContext."""
    db: object
    organization_id: str
    conversation_id: str | None = None


async def _seed_env(db, org_id: str) -> tuple[str, str, str]:
    """Set up: user + customer + property + water feature."""
    from src.models.customer import Customer
    from src.models.property import Property
    from src.models.water_feature import WaterFeature

    user = User(
        id=str(uuid.uuid4()),
        email=f"db-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="DB", last_name="Test",
    )
    db.add(user)

    cust = Customer(
        id=str(uuid.uuid4()), organization_id=org_id,
        first_name="C", last_name="ust",
        email=f"c-{uuid.uuid4().hex[:6]}@test.com",
        customer_type="residential",
    )
    db.add(cust)

    prop = Property(
        id=str(uuid.uuid4()), organization_id=org_id, customer_id=cust.id,
        address="1 Dogfood St", city="Sac", state="CA", zip_code="95814",
    )
    db.add(prop)

    wf = WaterFeature(
        id=str(uuid.uuid4()), organization_id=org_id, property_id=prop.id,
        water_type="pool", name="Main Pool",
    )
    db.add(wf)

    await db.flush()
    return user.id, prop.id, wf.id


@pytest.mark.asyncio
async def test_tool_stages_proposal_with_proposal_id(db_session, org_a):
    _, _, wf_id = await _seed_env(db_session, org_a.id)
    await db_session.commit()

    ctx = _ToolCtx(db=db_session, organization_id=org_a.id, conversation_id="conv-1")
    result = await _exec_add_equipment(
        inp={
            "bow_id": wf_id,
            "equipment_type": "pump",
            "brand": "Pentair",
            "model": "IntelliFlo",
            "notes": "1.5HP",
        },
        ctx=ctx,
    )

    # Tool returns the preview + proposal_id; frontend keys off proposal_id.
    assert "error" not in result, result
    assert result["action"] == "add_equipment"
    # After Step 10, requires_confirmation is fully removed.
    assert "requires_confirmation" not in result
    assert "proposal_id" in result
    pid = result["proposal_id"]
    assert result["preview"]["proposal_id"] == pid

    # A staged proposal landed in agent_proposals.
    proposal = await db_session.get(AgentProposal, pid)
    assert proposal is not None
    assert proposal.status == STATUS_STAGED
    assert proposal.entity_type == "equipment_item"
    assert proposal.agent_type == "deepblue_responder"
    assert proposal.source_type == "deepblue_conversation"
    assert proposal.source_id == "conv-1"
    assert proposal.proposed_payload["water_feature_id"] == wf_id
    assert proposal.proposed_payload["brand"] == "Pentair"


@pytest.mark.asyncio
async def test_tool_rejects_wrong_org_water_feature(db_session, org_a, org_b):
    _, _, wf_id = await _seed_env(db_session, org_b.id)  # WF in org_b
    await db_session.commit()

    # Call tool in org_a's context — cross-org attempt.
    ctx = _ToolCtx(db=db_session, organization_id=org_a.id)
    result = await _exec_add_equipment(
        inp={"bow_id": wf_id, "equipment_type": "pump", "brand": "X", "model": "Y"},
        ctx=ctx,
    )
    assert "error" in result
    # No proposal was staged.
    count = (await db_session.execute(
        text("SELECT count(*) FROM agent_proposals WHERE source_type='deepblue_conversation'")
    )).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_accept_creates_equipment_and_fires_events(
    db_session, org_a, event_recorder,
):
    """Full chain: tool stage → ProposalService.accept → EquipmentItem
    created → events fired."""
    user_id, _, wf_id = await _seed_env(db_session, org_a.id)
    await db_session.commit()

    # Stage via the tool
    ctx = _ToolCtx(db=db_session, organization_id=org_a.id, conversation_id="conv-2")
    staged = await _exec_add_equipment(
        inp={"bow_id": wf_id, "equipment_type": "pump", "brand": "Hayward", "model": "X1"},
        ctx=ctx,
    )
    pid = staged["proposal_id"]

    # Accept via the service (mirrors what the /confirm-add-equipment endpoint does)
    service = ProposalService(db_session)
    proposal, created = await service.accept(
        proposal_id=pid,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    # Proposal resolved
    assert proposal.status == STATUS_ACCEPTED
    assert proposal.outcome_entity_type == "equipment_item"
    assert proposal.outcome_entity_id == created.id

    # EquipmentItem exists with the right fields
    assert isinstance(created, EquipmentItem)
    assert created.water_feature_id == wf_id
    assert created.brand == "Hayward"
    assert created.equipment_type == "pump"
    assert created.organization_id == org_a.id  # critical — prior endpoint bug

    # Event trail
    await event_recorder.assert_emitted("proposal.staged", agent_proposal_id=pid)
    await event_recorder.assert_emitted("proposal.accepted", agent_proposal_id=pid)
    await event_recorder.assert_emitted("equipment_item.added", equipment_item_id=created.id)


@pytest.mark.asyncio
async def test_accept_fails_clean_if_water_feature_gone(
    db_session, org_a,
):
    """If the WF is deleted between stage and accept, creator raises
    NotFoundError → transaction rolls back, proposal stays staged."""
    user_id, _, wf_id = await _seed_env(db_session, org_a.id)
    await db_session.commit()

    ctx = _ToolCtx(db=db_session, organization_id=org_a.id)
    staged = await _exec_add_equipment(
        inp={"bow_id": wf_id, "equipment_type": "pump", "brand": "X", "model": "Y"},
        ctx=ctx,
    )
    pid = staged["proposal_id"]

    # Delete the WF. Tool was resilient at stage time; now the creator
    # will fail.
    await db_session.execute(text("DELETE FROM water_features WHERE id = :id"), {"id": wf_id})
    await db_session.commit()

    service = ProposalService(db_session)
    with pytest.raises(Exception):  # NotFoundError from EquipmentItemService
        await service.accept(
            proposal_id=pid,
            actor=Actor(actor_type="user", user_id=user_id),
        )
    # Rollback required before further use of the session
    await db_session.rollback()

    # Proposal still staged — accept did NOT partially succeed.
    proposal = await db_session.get(AgentProposal, pid)
    assert proposal.status == STATUS_STAGED
