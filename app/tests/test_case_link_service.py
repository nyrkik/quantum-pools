"""Tests for ServiceCaseService.set_entity_case — Phase 1 of entity-connections-plan.

Invariants verified:
- link/unlink is idempotent (same call twice is a no-op)
- Cross-org mutations raise LookupError (can't touch another org's data)
- Counts on ServiceCase stay in sync with actual FKs after arbitrary sequences
- All five linkable types work end-to-end
- Moving an entity between cases updates both source and target counts
"""

from __future__ import annotations

import pytest
import uuid
from datetime import datetime, timezone

from src.services.service_case_service import ServiceCaseService
from src.models.service_case import ServiceCase
from src.models.agent_action import AgentAction
from src.models.agent_thread import AgentThread
from src.models.invoice import Invoice
from src.models.internal_message import InternalThread
from src.models.deepblue_conversation import DeepBlueConversation


async def _make_case(db, org, title="Test Case") -> ServiceCase:
    svc = ServiceCaseService(db)
    case = await svc.create(org_id=org.id, title=title, source="manual")
    await db.commit()
    return case


async def _make_job(db, org, case_id=None) -> AgentAction:
    action = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        action_type="repair",
        description="Fix the thing",
        status="open",
        case_id=case_id,
    )
    db.add(action)
    await db.commit()
    return action


async def _make_thread(db, org, case_id=None) -> AgentThread:
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        thread_key=f"tk-{uuid.uuid4().hex[:8]}",
        contact_email="a@b.com",
        subject="Test",
        status="new",
        case_id=case_id,
    )
    db.add(thread)
    await db.commit()
    return thread


async def _make_invoice(db, org, case_id=None) -> Invoice:
    inv = Invoice(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        customer_id=None,
        invoice_number=f"T-{uuid.uuid4().hex[:6]}",
        status="draft",
        document_type="invoice",
        issue_date=datetime.now(timezone.utc).date(),
        total=100.0,
        case_id=case_id,
    )
    db.add(inv)
    await db.commit()
    return inv


async def _make_internal_thread(db, org, case_id=None) -> InternalThread:
    it = InternalThread(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        created_by_user_id=None,
        participant_ids=[],
        subject="Team question",
        case_id=case_id,
    )
    db.add(it)
    await db.commit()
    return it


async def _make_deepblue_conv(db, org, user_id=None, case_id=None) -> DeepBlueConversation:
    # DeepBlueConversation.user_id is NOT NULL; create a user if needed.
    if not user_id:
        from src.models.user import User
        u = User(
            id=str(uuid.uuid4()),
            email=f"u-{uuid.uuid4().hex[:6]}@test.com",
            hashed_password="x",
            first_name="T",
            last_name="U",
        )
        db.add(u)
        await db.commit()
        user_id = u.id
    conv = DeepBlueConversation(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        user_id=user_id,
        title="Test convo",
        case_id=case_id,
    )
    db.add(conv)
    await db.commit()
    return conv


@pytest.mark.asyncio
async def test_link_invoice_updates_counts(db_session, org_a):
    case = await _make_case(db_session, org_a)
    inv = await _make_invoice(db_session, org_a)

    svc = ServiceCaseService(db_session)
    result = await svc.set_entity_case(org_a.id, "invoice", inv.id, case.id)
    await db_session.commit()

    assert result["changed"] is True
    await db_session.refresh(case)
    assert case.invoice_count == 1
    assert case.total_invoiced == 100.0


@pytest.mark.asyncio
async def test_link_is_idempotent(db_session, org_a):
    case = await _make_case(db_session, org_a)
    job = await _make_job(db_session, org_a)

    svc = ServiceCaseService(db_session)
    r1 = await svc.set_entity_case(org_a.id, "job", job.id, case.id)
    r2 = await svc.set_entity_case(org_a.id, "job", job.id, case.id)
    await db_session.commit()

    assert r1["changed"] is True
    assert r2["changed"] is False
    await db_session.refresh(case)
    assert case.job_count == 1


@pytest.mark.asyncio
async def test_cross_org_link_blocked(db_session, org_a, org_b):
    """A user in org A cannot link org A's case to org B's entity."""
    case_a = await _make_case(db_session, org_a)
    invoice_b = await _make_invoice(db_session, org_b)

    svc = ServiceCaseService(db_session)
    with pytest.raises(LookupError):
        await svc.set_entity_case(org_a.id, "invoice", invoice_b.id, case_a.id)

    await db_session.refresh(invoice_b)
    assert invoice_b.case_id is None


@pytest.mark.asyncio
async def test_cross_org_target_case_blocked(db_session, org_a, org_b):
    """A user in org A cannot link to a case from org B."""
    case_b = await _make_case(db_session, org_b)
    invoice_a = await _make_invoice(db_session, org_a)

    svc = ServiceCaseService(db_session)
    with pytest.raises(LookupError):
        await svc.set_entity_case(org_a.id, "invoice", invoice_a.id, case_b.id)

    await db_session.refresh(invoice_a)
    assert invoice_a.case_id is None


@pytest.mark.asyncio
async def test_unlink_clears_case_and_updates_counts(db_session, org_a):
    case = await _make_case(db_session, org_a)
    thread = await _make_thread(db_session, org_a, case_id=case.id)
    svc = ServiceCaseService(db_session)
    await svc.update_counts(case.id)
    await db_session.commit()
    await db_session.refresh(case)
    assert case.thread_count == 1

    await svc.set_entity_case(org_a.id, "thread", thread.id, None)
    await db_session.commit()
    await db_session.refresh(case)
    await db_session.refresh(thread)
    assert thread.case_id is None
    assert case.thread_count == 0


@pytest.mark.asyncio
async def test_move_between_cases_updates_both(db_session, org_a):
    case_1 = await _make_case(db_session, org_a, title="Case 1")
    case_2 = await _make_case(db_session, org_a, title="Case 2")
    job = await _make_job(db_session, org_a, case_id=case_1.id)

    svc = ServiceCaseService(db_session)
    await svc.update_counts(case_1.id)
    await db_session.commit()
    await db_session.refresh(case_1)
    assert case_1.job_count == 1

    await svc.set_entity_case(org_a.id, "job", job.id, case_2.id)
    await db_session.commit()
    await db_session.refresh(case_1)
    await db_session.refresh(case_2)

    assert case_1.job_count == 0
    assert case_2.job_count == 1


@pytest.mark.asyncio
async def test_all_five_linkable_types(db_session, org_a):
    """Sanity check: each of the five supported types can be linked and counted."""
    case = await _make_case(db_session, org_a)
    svc = ServiceCaseService(db_session)

    job = await _make_job(db_session, org_a)
    thread = await _make_thread(db_session, org_a)
    inv = await _make_invoice(db_session, org_a)
    it = await _make_internal_thread(db_session, org_a)
    conv = await _make_deepblue_conv(db_session, org_a)

    for t, eid in [
        ("job", job.id),
        ("thread", thread.id),
        ("invoice", inv.id),
        ("internal_thread", it.id),
        ("deepblue_conversation", conv.id),
    ]:
        await svc.set_entity_case(org_a.id, t, eid, case.id)
    await db_session.commit()

    await db_session.refresh(case)
    assert case.job_count == 1
    assert case.thread_count == 1
    assert case.invoice_count == 1
    assert case.internal_thread_count == 1
    assert case.deepblue_conversation_count == 1


@pytest.mark.asyncio
async def test_unknown_type_raises(db_session, org_a):
    case = await _make_case(db_session, org_a)
    svc = ServiceCaseService(db_session)
    with pytest.raises(ValueError):
        await svc.set_entity_case(org_a.id, "bogus", "x", case.id)


@pytest.mark.asyncio
async def test_invalid_entity_id_raises(db_session, org_a):
    case = await _make_case(db_session, org_a)
    svc = ServiceCaseService(db_session)
    with pytest.raises(LookupError):
        await svc.set_entity_case(org_a.id, "invoice", "does-not-exist", case.id)
