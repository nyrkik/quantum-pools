"""Tests for the 4 Phase-2 entity-type creators.

Each creator is exercised through `ProposalService.accept` so we
verify the full chain: registry lookup → schema validation → creator
invocation → entity creation → event emission.

Payload shapes come from the Pydantic schemas defined alongside each
creator; we test happy paths plus schema rejection for each.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text

from src.models.agent_action import AgentAction
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.equipment_item import EquipmentItem
from src.models.invoice import Invoice
from src.models.job_invoice import JobInvoice
from src.models.property import Property
from src.models.user import User
from src.models.water_feature import WaterFeature
from src.services.events.platform_event_service import Actor
from src.services.proposals import ProposalService  # triggers registry load


async def _seed_user(db) -> str:
    u = User(
        id=str(uuid.uuid4()),
        email=f"pc-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="Proposal", last_name="Creator",
    )
    db.add(u); await db.flush()
    return u.id


async def _seed_customer_property_wf(db, org_id: str) -> tuple[str, str, str]:
    cust = Customer(
        id=str(uuid.uuid4()), organization_id=org_id,
        first_name="Cust", last_name="omer",
        email=f"c-{uuid.uuid4().hex[:6]}@test.com",
        customer_type="residential",
    )
    db.add(cust)
    prop = Property(
        id=str(uuid.uuid4()), organization_id=org_id, customer_id=cust.id,
        address="1 Test", city="Sac", state="CA", zip_code="95814",
    )
    db.add(prop)
    wf = WaterFeature(
        id=str(uuid.uuid4()), organization_id=org_id, property_id=prop.id,
        water_type="pool",
    )
    db.add(wf)
    await db.flush()
    return cust.id, prop.id, wf.id


# --- job -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_creator_produces_agent_action(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    cust_id, _, _ = await _seed_customer_property_wf(db_session, org_a.id)
    # Job needs to live inside a case — use find_or_create path via add_job
    service = ProposalService(db_session)
    await service.stage(
        org_id=org_a.id,
        agent_type="job_evaluator",
        entity_type="job",
        source_type="test",
        source_id=None,
        proposed_payload={
            "action_type": "repair",
            "description": "Replace pump seal — Test St",
            "customer_id": cust_id,
        },
    )
    await db_session.commit()

    p_id = (await db_session.execute(
        text("SELECT id FROM agent_proposals WHERE entity_type='job' ORDER BY created_at DESC LIMIT 1")
    )).scalar()
    p_resolved, created = await service.accept(
        proposal_id=p_id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    # Entity exists as an AgentAction
    assert isinstance(created, AgentAction)
    assert created.action_type == "repair"
    assert created.customer_id == cust_id
    # Outcome fields stamped
    assert p_resolved.outcome_entity_id == created.id
    # job.created event fired (from add_job, not ProposalService)
    await event_recorder.assert_emitted("job.created", job_id=created.id)
    # proposal.accepted event fired
    await event_recorder.assert_emitted("proposal.accepted", agent_proposal_id=p_id)


@pytest.mark.asyncio
async def test_job_creator_rejects_invalid_payload(db_session, org_a):
    service = ProposalService(db_session)
    with pytest.raises(Exception):  # pydantic ValidationError
        await service.stage(
            org_id=org_a.id, agent_type="x", entity_type="job",
            source_type="t", source_id=None,
            # Missing required action_type + description
            proposed_payload={"customer_id": "c"},
        )


# --- estimate ------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_creator_produces_invoice(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    cust_id, _, _ = await _seed_customer_property_wf(db_session, org_a.id)
    service = ProposalService(db_session)

    p = await service.stage(
        org_id=org_a.id,
        agent_type="estimate_generator",
        entity_type="estimate",
        source_type="test",
        source_id=None,
        proposed_payload={
            "customer_id": cust_id,
            "subject": "Pump replacement",
            "line_items": [
                {"description": "1HP pump + install", "quantity": 1, "unit_price": 850.00},
                {"description": "Labor (2h)", "quantity": 2, "unit_price": 125.00},
            ],
        },
    )
    await db_session.commit()

    p_resolved, created = await service.accept(
        proposal_id=p.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    assert isinstance(created, Invoice)
    assert created.document_type == "estimate"
    assert created.customer_id == cust_id
    # 850 + 2*125 = 1100
    assert float(created.subtotal) == 1100.00
    # invoice.created event fired
    await event_recorder.assert_emitted("invoice.created", invoice_id=created.id)


@pytest.mark.asyncio
async def test_estimate_creator_rejects_empty_line_items(db_session, org_a):
    service = ProposalService(db_session)
    with pytest.raises(Exception):
        await service.stage(
            org_id=org_a.id, agent_type="x", entity_type="estimate",
            source_type="t", source_id=None,
            proposed_payload={"customer_id": "c", "line_items": []},  # empty — rejected
        )


async def _seed_thread(db, org_id: str, customer_id: str | None = None) -> str:
    t = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"est-{uuid.uuid4().hex[:8]}",
        contact_email="client@example.com",
        subject="Pump is leaking",
        status="pending",
        category="service_request",
        message_count=1,
        last_direction="inbound",
        matched_customer_id=customer_id,
        customer_name="Test Customer" if customer_id else None,
    )
    db.add(t)
    await db.flush()
    return t.id


async def _has_link(db, action_id: str, invoice_id: str) -> bool:
    row = (await db.execute(
        select(JobInvoice).where(
            JobInvoice.action_id == action_id,
            JobInvoice.invoice_id == invoice_id,
        )
    )).scalar_one_or_none()
    return row is not None


@pytest.mark.asyncio
async def test_estimate_creator_links_to_existing_thread_job(db_session, org_a):
    """thread_id with an existing repair job on the thread → invoice linked to that job."""
    user_id = await _seed_user(db_session)
    cust_id, _, _ = await _seed_customer_property_wf(db_session, org_a.id)
    thread_id = await _seed_thread(db_session, org_a.id, customer_id=cust_id)
    existing_job = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        thread_id=thread_id,
        customer_id=cust_id,
        action_type="repair",
        description="Replace pump seal",
        status="open",
    )
    db_session.add(existing_job)
    await db_session.flush()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="estimate_generator",
        entity_type="estimate",
        source_type="thread",
        source_id=thread_id,
        proposed_payload={
            "customer_id": cust_id,
            "thread_id": thread_id,
            "subject": "Pump repair",
            "line_items": [{"description": "Labor", "quantity": 1, "unit_price": 250.00}],
        },
    )
    await db_session.commit()

    _, created = await service.accept(
        proposal_id=p.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    assert isinstance(created, Invoice)
    assert await _has_link(db_session, existing_job.id, created.id)


@pytest.mark.asyncio
async def test_estimate_creator_falls_back_to_customer_open_job(db_session, org_a):
    """No thread job, but matched customer has an open site_visit → invoice linked to that."""
    user_id = await _seed_user(db_session)
    cust_id, _, _ = await _seed_customer_property_wf(db_session, org_a.id)
    thread_id = await _seed_thread(db_session, org_a.id, customer_id=cust_id)
    customer_job = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=cust_id,
        action_type="site_visit",
        description="Initial visit for quote",
        status="open",
    )
    db_session.add(customer_job)
    await db_session.flush()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="estimate_generator",
        entity_type="estimate",
        source_type="thread",
        source_id=thread_id,
        proposed_payload={
            "customer_id": cust_id,
            "thread_id": thread_id,
            "subject": "Initial quote",
            "line_items": [{"description": "Assessment", "quantity": 1, "unit_price": 150.00}],
        },
    )
    await db_session.commit()

    _, created = await service.accept(
        proposal_id=p.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    assert isinstance(created, Invoice)
    assert await _has_link(db_session, customer_job.id, created.id)


@pytest.mark.asyncio
async def test_estimate_creator_creates_new_bid_job_when_none_exists(
    db_session, org_a, event_recorder,
):
    """No thread job, no matched-customer job → new bid job created + linked."""
    user_id = await _seed_user(db_session)
    cust_id, _, _ = await _seed_customer_property_wf(db_session, org_a.id)
    thread_id = await _seed_thread(db_session, org_a.id, customer_id=cust_id)

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="estimate_generator",
        entity_type="estimate",
        source_type="thread",
        source_id=thread_id,
        proposed_payload={
            "customer_id": cust_id,
            "thread_id": thread_id,
            "subject": "Weekly service quote",
            "line_items": [{"description": "Service", "quantity": 4, "unit_price": 125.00}],
        },
    )
    await db_session.commit()

    _, created = await service.accept(
        proposal_id=p.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    # Confirm a bid job got created for this thread + customer, linked to the invoice
    new_job = (await db_session.execute(
        select(AgentAction).where(
            AgentAction.thread_id == thread_id,
            AgentAction.action_type == "bid",
        )
    )).scalar_one_or_none()
    assert new_job is not None
    assert new_job.customer_id == cust_id
    assert new_job.job_path == "customer"
    assert await _has_link(db_session, new_job.id, created.id)
    await event_recorder.assert_emitted("job.created", job_id=new_job.id)


# --- equipment_item ------------------------------------------------------


@pytest.mark.asyncio
async def test_equipment_item_creator_produces_row(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    _, _, wf_id = await _seed_customer_property_wf(db_session, org_a.id)
    service = ProposalService(db_session)

    p = await service.stage(
        org_id=org_a.id,
        agent_type="equipment_resolver",
        entity_type="equipment_item",
        source_type="test",
        source_id=None,
        proposed_payload={
            "water_feature_id": wf_id,
            "equipment_type": "pump",
            "brand": "Pentair",
            "model": "IntelliFlo",
            "horsepower": 1.5,
        },
    )
    await db_session.commit()

    p_resolved, created = await service.accept(
        proposal_id=p.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    assert isinstance(created, EquipmentItem)
    assert created.equipment_type == "pump"
    assert created.brand == "Pentair"
    assert created.water_feature_id == wf_id
    # equipment_item.added event fired
    await event_recorder.assert_emitted(
        "equipment_item.added", equipment_item_id=created.id
    )


# --- org_config ----------------------------------------------------------


@pytest.mark.asyncio
async def test_org_config_creator_updates_scalar(db_session, org_a, event_recorder):
    user_id = await _seed_user(db_session)
    service = ProposalService(db_session)

    # Pick a setting and flip it
    p = await service.stage(
        org_id=org_a.id,
        agent_type="workflow_observer",
        entity_type="org_config",
        source_type="observation_batch",
        source_id=None,
        proposed_payload={"key": "agent_enabled", "value": True},
    )
    await db_session.commit()

    p_resolved, org_back = await service.accept(
        proposal_id=p.id,
        actor=Actor(actor_type="user", user_id=user_id),
    )
    await db_session.commit()

    await db_session.refresh(org_a)
    assert org_a.agent_enabled is True
    # settings.changed event fired (taxonomy-conforming shape)
    event = await event_recorder.assert_emitted("settings.changed")
    assert event["payload"]["area"] == "org_config"
    assert event["payload"]["fields_changed"] == ["agent_enabled"]


@pytest.mark.asyncio
async def test_org_config_creator_rejects_unknown_key(db_session, org_a):
    service = ProposalService(db_session)
    with pytest.raises(Exception):
        await service.stage(
            org_id=org_a.id, agent_type="x", entity_type="org_config",
            source_type="t", source_id=None,
            proposed_payload={"key": "stripe_customer_id", "value": "cus_X"},  # not allowed
        )


# --- registry smoke ------------------------------------------------------


@pytest.mark.asyncio
async def test_all_four_phase_2_entity_types_registered():
    from src.services.proposals.registry import known_entity_types
    types = known_entity_types()
    # All 4 Phase-2 creators are registered on import
    for expected in ("job", "estimate", "equipment_item", "org_config"):
        assert expected in types, f"{expected!r} missing from registry"
