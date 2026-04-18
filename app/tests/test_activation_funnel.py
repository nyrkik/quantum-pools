"""Integration tests — activation funnel.

Covers Phase 1 Step 8 per docs/ai-platform-phase-1.md §6.12 +
docs/event-taxonomy.md §8.13:

- emit_if_first() fires an activation event ONCE per org ever.
- Subsequent "first" calls are no-ops.
- Different orgs get their own independent first-event.
- minutes_since_prior_milestone is populated relative to the most
  recent prior funnel milestone for the same org.
- Service-layer integration: register, customer create, visit complete,
  invoice send, payment recorded each fire the correct milestone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.services.events.activation_tracker import emit_if_first, FUNNEL_ORDER


# ---------------------------------------------------------------------------
# emit_if_first — core behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_if_first_fires_the_first_time(db_session, org_a, event_recorder):
    result = await emit_if_first(
        db_session,
        "activation.account_created",
        organization_id=org_a.id,
        entity_refs={"user_id": "u-1"},
        source="test",
    )
    assert result is True
    await db_session.commit()

    event = await event_recorder.assert_emitted("activation.account_created")
    assert event["organization_id"] == org_a.id
    assert event["entity_refs"]["user_id"] == "u-1"
    assert event["payload"].get("source") == "test"
    # account_created is the first milestone — no prior
    assert "minutes_since_prior_milestone" not in event["payload"]


@pytest.mark.asyncio
async def test_emit_if_first_noop_on_second_call(db_session, org_a, event_recorder):
    first = await emit_if_first(
        db_session, "activation.account_created",
        organization_id=org_a.id, source="test",
    )
    await db_session.commit()
    second = await emit_if_first(
        db_session, "activation.account_created",
        organization_id=org_a.id, source="test",
    )
    await db_session.commit()

    assert first is True
    assert second is False
    events = await event_recorder.all_of_type("activation.account_created")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_emit_if_first_is_per_org(db_session, org_a, org_b, event_recorder):
    """Org A's account_created doesn't block org B's."""
    a_result = await emit_if_first(
        db_session, "activation.account_created",
        organization_id=org_a.id, source="test",
    )
    b_result = await emit_if_first(
        db_session, "activation.account_created",
        organization_id=org_b.id, source="test",
    )
    await db_session.commit()

    assert a_result is True
    assert b_result is True
    events = await event_recorder.all_of_type("activation.account_created")
    assert len(events) == 2
    orgs = sorted(e["organization_id"] for e in events)
    assert orgs == sorted([org_a.id, org_b.id])


@pytest.mark.asyncio
async def test_emit_if_first_skips_when_no_org(db_session, event_recorder):
    """Platform-scoped (no org) activation events are a no-op — activation
    milestones only make sense within an org's funnel."""
    result = await emit_if_first(
        db_session, "activation.account_created",
        organization_id="",  # empty
        source="test",
    )
    assert result is False
    await db_session.commit()
    assert (await event_recorder.all_of_type("activation.account_created")) == []


# ---------------------------------------------------------------------------
# Funnel ordering + minutes_since_prior_milestone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minutes_since_prior_milestone_computed(
    db_session, org_a, event_recorder
):
    """When a later milestone fires, its payload includes the elapsed time
    since the most recent prior milestone for the same org."""
    # Seed a prior milestone 10 minutes ago by inserting directly (emit
    # would use NOW()).
    ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.execute(
        text("""
            INSERT INTO platform_events
              (id, organization_id, actor_type, event_type, level,
               entity_refs, payload, created_at)
            VALUES
              (:id, :org, 'system', 'activation.account_created', 'system_action',
               '{}'::jsonb, '{}'::jsonb, :ts)
        """),
        {"id": str(uuid.uuid4()), "org": org_a.id, "ts": ten_min_ago},
    )
    await db_session.commit()

    await emit_if_first(
        db_session, "activation.first_customer_added",
        organization_id=org_a.id, source="test",
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("activation.first_customer_added")
    assert "minutes_since_prior_milestone" in event["payload"]
    # Loose bound: somewhere between 9 and 12 minutes (clock skew + test timing)
    assert 9 <= event["payload"]["minutes_since_prior_milestone"] <= 12


@pytest.mark.asyncio
async def test_funnel_order_is_canonical(db_session):
    """Sanity: the FUNNEL_ORDER tuple reflects the documented sequence."""
    assert FUNNEL_ORDER == (
        "activation.account_created",
        "activation.first_customer_added",
        "activation.first_visit_completed",
        "activation.first_invoice_sent",
        "activation.first_payment_received",
        "activation.first_ai_proposal_accepted",
    )


# ---------------------------------------------------------------------------
# Service-layer integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_service_create_fires_first_customer_added(
    db_session, org_a, event_recorder
):
    from src.services.customer_service import CustomerService

    svc = CustomerService(db_session)
    await svc.create(
        org_a.id,
        first_name="A", last_name="B",
        email="a@b.com", customer_type="residential",
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("activation.first_customer_added")
    assert event["organization_id"] == org_a.id


@pytest.mark.asyncio
async def test_customer_service_second_customer_is_noop(
    db_session, org_a, event_recorder
):
    from src.services.customer_service import CustomerService

    svc = CustomerService(db_session)
    await svc.create(org_a.id, first_name="A", last_name="B", email="a@b.com", customer_type="residential")
    await svc.create(org_a.id, first_name="C", last_name="D", email="c@d.com", customer_type="residential")
    await db_session.commit()

    # Only ONE activation event even though two customers were created
    events = await event_recorder.all_of_type("activation.first_customer_added")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_invoice_send_estimate_does_not_fire_activation(
    db_session, org_a, event_recorder
):
    """Sending an ESTIMATE should NOT fire activation.first_invoice_sent —
    that milestone is for invoices specifically."""
    # Seed a minimal customer + estimate
    from src.models.customer import Customer
    from src.models.invoice import Invoice

    cust = Customer(
        id=str(uuid.uuid4()), organization_id=org_a.id,
        first_name="A", last_name="B", email="a@b.com",
        customer_type="residential",
    )
    db_session.add(cust)

    from datetime import date
    estimate = Invoice(
        id=str(uuid.uuid4()), organization_id=org_a.id, customer_id=cust.id,
        document_type="estimate", status="draft",
        issue_date=date.today(),
        subtotal=100.0, total=100.0, balance=100.0,
    )
    db_session.add(estimate)
    await db_session.commit()

    from src.services.invoice_service import InvoiceService
    svc = InvoiceService(db_session)
    await svc.send(org_a.id, estimate.id)
    await db_session.commit()

    # No activation.first_invoice_sent — it was an estimate
    assert (await event_recorder.all_of_type("activation.first_invoice_sent")) == []


@pytest.mark.asyncio
async def test_invoice_send_real_invoice_fires_activation(
    db_session, org_a, event_recorder
):
    from src.models.customer import Customer
    from src.models.invoice import Invoice

    cust = Customer(
        id=str(uuid.uuid4()), organization_id=org_a.id,
        first_name="A", last_name="B", email="a@b.com",
        customer_type="residential",
    )
    db_session.add(cust)

    from datetime import date
    invoice = Invoice(
        id=str(uuid.uuid4()), organization_id=org_a.id, customer_id=cust.id,
        document_type="invoice", status="draft",
        issue_date=date.today(),
        subtotal=100.0, total=100.0, balance=100.0,
    )
    db_session.add(invoice)
    await db_session.commit()

    from src.services.invoice_service import InvoiceService
    svc = InvoiceService(db_session)
    await svc.send(org_a.id, invoice.id)
    await db_session.commit()

    event = await event_recorder.assert_emitted("activation.first_invoice_sent")
    assert event["entity_refs"]["invoice_id"] == invoice.id


@pytest.mark.asyncio
async def test_estimate_conversion_fires_first_invoice_sent(
    db_session, org_a, event_recorder
):
    """When an estimate gets converted to an invoice via the API
    /invoices/{id}/convert-to-invoice path, that's the org's first sent
    invoice if they had no prior — activation.first_invoice_sent should
    fire from that path even though it bypasses InvoiceService.send.

    We test the core emit path (not the full HTTP route), since the
    estimate-conversion endpoint is thin and the activation logic lives
    in the emit_if_first helper + the source tag."""
    await emit_if_first(
        db_session,
        "activation.first_invoice_sent",
        organization_id=org_a.id,
        entity_refs={"invoice_id": "inv-1"},
        source="estimate_conversion",
    )
    await db_session.commit()
    event = await event_recorder.assert_emitted("activation.first_invoice_sent")
    assert event["payload"]["source"] == "estimate_conversion"


@pytest.mark.asyncio
async def test_stripe_source_variants_all_count_as_first_payment(
    db_session, org_a, event_recorder
):
    """The 3 Stripe creation sites each pass a different `source`
    (stripe_checkout / stripe_autopay_webhook / stripe_autopay_internal),
    but they all count toward the same activation.first_payment_received
    milestone — only ONE fires per org ever."""
    first = await emit_if_first(
        db_session, "activation.first_payment_received",
        organization_id=org_a.id, source="stripe_checkout",
    )
    await db_session.commit()
    second = await emit_if_first(
        db_session, "activation.first_payment_received",
        organization_id=org_a.id, source="stripe_autopay_webhook",
    )
    third = await emit_if_first(
        db_session, "activation.first_payment_received",
        organization_id=org_a.id, source="stripe_autopay_internal",
    )
    await db_session.commit()
    assert (first, second, third) == (True, False, False)
    events = await event_recorder.all_of_type("activation.first_payment_received")
    assert len(events) == 1
    assert events[0]["payload"]["source"] == "stripe_checkout"


@pytest.mark.asyncio
async def test_auth_service_register_fires_account_created(
    db_session, event_recorder
):
    from src.services.auth_service import AuthService

    svc = AuthService(db_session)
    user, org = await svc.register(
        email=f"new-{uuid.uuid4().hex[:8]}@test.com",
        password="testpass123",
        first_name="New",
        last_name="User",
        organization_name=f"New Org {uuid.uuid4().hex[:6]}",
    )

    event = await event_recorder.assert_emitted("activation.account_created")
    assert event["organization_id"] == org.id
    assert event["entity_refs"]["user_id"] == user.id
