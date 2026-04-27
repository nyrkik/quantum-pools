"""Tests for PaymentMatcher — Phase 1 payment reconciliation.

Covers the scoring engine + decision logic + auto-match Payment
creation + pending-vs-completed lifecycle. Uses synthetic fixtures
(no real Entrata bodies needed — those are tested separately on the
parser).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.invoice import Invoice, InvoiceStatus
from src.models.parsed_payment import ParsedPayment, ParsedPaymentStatus
from src.models.payment import Payment, PaymentStatus
from src.models.property import Property
from src.services.payments.matcher import (
    AUTO_MATCH_FLOOR,
    PROPOSE_FLOOR,
    match_parsed_payments,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


async def _seed_customer(db, org_id: str, *, company: str | None = None,
                         first: str = "Pat", last: str = "Manager",
                         balance: float = 0.0) -> Customer:
    c = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        first_name=first, last_name=last,
        company_name=company,
        balance=balance,
    )
    db.add(c)
    await db.flush()
    return c


async def _seed_property(db, org_id: str, customer_id: str, name: str) -> Property:
    p = Property(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        customer_id=customer_id,
        name=name,
        address="100 Test St", city="Sac", state="CA", zip_code="95814",
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_invoice(db, org_id: str, customer_id: str, *,
                       total: float, invoice_number: str = "INV-100",
                       status: str = InvoiceStatus.sent.value) -> Invoice:
    inv = Invoice(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        customer_id=customer_id,
        invoice_number=invoice_number,
        status=status,
        issue_date=date.today(),
        subtotal=total, total=total, balance=total, amount_paid=0.0,
    )
    db.add(inv)
    await db.flush()
    return inv


async def _seed_message(db, org_id: str) -> AgentMessage:
    """Minimal AgentMessage so parsed_payments rows can FK to it."""
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"test-{uuid.uuid4().hex[:8]}",
        contact_email="payer@example.com",
        subject="Payment", status="pending", category="billing",
        message_count=1, last_direction="inbound",
    )
    db.add(thread)
    await db.flush()
    msg = AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        direction="inbound",
        from_email="system@entrata.com", to_email="contact@sapphire-pools.com",
        subject="Payment Submitted", body="...",
        category="billing", status="pending",
        thread_id=thread.id,
    )
    db.add(msg)
    await db.flush()
    return msg


def _seed_parsed(msg: AgentMessage, *, amount=None, payer=None, property_hint=None,
                 invoice_hint=None, payment_method=None,
                 payment_date=None, reference_number=None) -> ParsedPayment:
    return ParsedPayment(
        id=str(uuid.uuid4()),
        organization_id=msg.organization_id,
        agent_message_id=msg.id,
        processor="entrata",
        amount=amount,
        payer_name=payer,
        property_hint=property_hint,
        invoice_hint=invoice_hint,
        payment_method=payment_method,
        payment_date=payment_date,
        reference_number=reference_number,
        match_status=ParsedPaymentStatus.unmatched.value,
    )


# ---------------------------------------------------------------------------
# Empty / no-candidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_list_is_noop(db_session, org_a):
    await match_parsed_payments(db_session, parsed_payments=[])
    # No exceptions = pass.


@pytest.mark.asyncio
async def test_no_open_invoices_leaves_unmatched(db_session, org_a):
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(msg, amount=Decimal("100.00"), payer="Acme")
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()
    assert pp.match_status == ParsedPaymentStatus.unmatched.value


@pytest.mark.asyncio
async def test_amount_only_proposes_not_auto_matches(db_session, org_a):
    """Amount alone (no customer/property fuzzy hit) caps at 0.50 — must
    propose, never auto-match."""
    cust = await _seed_customer(db_session, org_a.id, company="Different Co LLC")
    inv = await _seed_invoice(db_session, org_a.id, cust.id, total=499.00)
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(
        msg, amount=Decimal("499.00"),
        payer="totally unrelated payer",
        property_hint="some property name no customer has",
        payment_method="ach",
    )
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()
    assert pp.match_status == ParsedPaymentStatus.proposed.value
    assert pp.match_confidence == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Auto-match paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_amount_plus_property_auto_matches_with_pending_check(db_session, org_a):
    cust = await _seed_customer(
        db_session, org_a.id, company="Greystar Property Mgmt", balance=0.0,
    )
    await _seed_property(db_session, org_a.id, cust.id, name="Arbor Ridge 2")
    inv = await _seed_invoice(
        db_session, org_a.id, cust.id, total=1776.00, invoice_number="INV-101",
    )
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(
        msg,
        amount=Decimal("1776.00"),
        payer="Arbor Ridge 2",
        property_hint="Arbor Ridge 2",
        payment_method="check",
        payment_date=date(2026, 4, 24),
        reference_number="3151",
    )
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()

    assert pp.match_status == ParsedPaymentStatus.auto_matched.value
    assert pp.payment_id is not None
    assert pp.matched_invoice_id == inv.id

    # Pending-check lifecycle: Payment created with status=pending,
    # invoice NOT marked paid yet, customer balance not bumped.
    payment = await db_session.get(Payment, pp.payment_id)
    assert payment is not None
    assert payment.status == PaymentStatus.pending.value
    assert payment.source_message_id == msg.id
    assert payment.amount == 1776.00

    refreshed_inv = await db_session.get(Invoice, inv.id)
    assert refreshed_inv.status == InvoiceStatus.sent.value  # not paid
    assert refreshed_inv.amount_paid == 0.0
    assert refreshed_inv.balance == 1776.00


@pytest.mark.asyncio
async def test_ach_auto_matches_as_completed_and_marks_invoice_paid(db_session, org_a):
    cust = await _seed_customer(db_session, org_a.id, company="ConAm Management Corporation")
    await _seed_property(db_session, org_a.id, cust.id, name="Coventry Park")
    inv = await _seed_invoice(db_session, org_a.id, cust.id, total=492.00, invoice_number="INV-200")
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(
        msg,
        amount=Decimal("492.00"),
        payer="ConAm Management Corporation",
        property_hint="Coventry Park",
        payment_method="ach",
        payment_date=date(2026, 4, 22),
    )
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()

    assert pp.match_status == ParsedPaymentStatus.auto_matched.value
    payment = await db_session.get(Payment, pp.payment_id)
    assert payment.status == PaymentStatus.completed.value

    refreshed_inv = await db_session.get(Invoice, inv.id)
    assert refreshed_inv.status == InvoiceStatus.paid.value
    assert refreshed_inv.amount_paid == 492.00
    assert refreshed_inv.balance == 0.0


@pytest.mark.asyncio
async def test_sapphire_shape_property_name_in_customer_first_name(db_session, org_a):
    """Real Sapphire data: Customer.first_name = property name,
    Customer.company_name = PM company, Property table mostly empty.

    The Entrata parser puts "Arbor Ridge 2" in payer_name + property_hint.
    The matcher must find this as a fuzzy match against
    Customer.first_name="Arbor Ridge 2" even though company_name is
    "Greystar" (which doesn't fuzzy-match the property name).
    """
    cust = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        company_name="Greystar",            # PM company
        first_name="Arbor Ridge 2",          # property name
        last_name="",
        balance=0.0,
    )
    db_session.add(cust)
    await db_session.flush()
    inv = await _seed_invoice(db_session, org_a.id, cust.id, total=1776.00)
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(
        msg,
        amount=Decimal("1776.00"),
        payer="Arbor Ridge 2",
        property_hint="Arbor Ridge 2",
        payment_method="ach",
        payment_date=date(2026, 4, 24),
    )
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()

    assert pp.match_status == ParsedPaymentStatus.auto_matched.value
    assert pp.payment_id is not None
    assert pp.match_confidence and pp.match_confidence >= 0.95


@pytest.mark.asyncio
async def test_invoice_number_exact_match_auto_even_without_amount_match(db_session, org_a):
    """Invoice# parser-supplied exact match scores 1.0 regardless of
    other fields. Useful for processors that DO supply our invoice
    numbers (Coupa via custom field; Yardi when configured)."""
    cust = await _seed_customer(db_session, org_a.id, company="Test Co")
    inv = await _seed_invoice(
        db_session, org_a.id, cust.id, total=250.00, invoice_number="QP-2026-0042",
    )
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(
        msg,
        amount=Decimal("250.00"),  # also matches; combined with invoice# = top score
        payer="Test Co",  # match
        invoice_hint="QP-2026-0042",
        payment_method="ach",
    )
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()
    assert pp.match_status == ParsedPaymentStatus.auto_matched.value
    assert pp.match_confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Ambiguous → propose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_invoices_same_amount_same_customer_proposes_not_auto(db_session, org_a):
    """Two open invoices for the same customer at the same amount —
    matcher can't tell which one this payment goes to. Should propose."""
    cust = await _seed_customer(db_session, org_a.id, company="Sunnyvale PM")
    await _seed_property(db_session, org_a.id, cust.id, name="Sunnyvale Apt")
    await _seed_invoice(db_session, org_a.id, cust.id, total=300.00, invoice_number="INV-A")
    await _seed_invoice(db_session, org_a.id, cust.id, total=300.00, invoice_number="INV-B")
    msg = await _seed_message(db_session, org_a.id)
    pp = _seed_parsed(
        msg,
        amount=Decimal("300.00"),
        payer="Sunnyvale PM",
        property_hint="Sunnyvale Apt",
        payment_method="ach",
    )
    db_session.add(pp)
    await db_session.commit()

    await match_parsed_payments(db_session, parsed_payments=[pp])
    await db_session.commit()

    # Both invoices tie at 0.95 (amount + customer fuzzy) and both
    # match property fuzzy. The "second_close" guard prevents auto-match.
    assert pp.match_status == ParsedPaymentStatus.proposed.value
    assert pp.payment_id is None
    assert pp.matched_invoice_id is not None  # still records the top candidate


# ---------------------------------------------------------------------------
# Threshold constants sanity
# ---------------------------------------------------------------------------


def test_thresholds_are_sane():
    assert PROPOSE_FLOOR < AUTO_MATCH_FLOOR < 1.0
    assert AUTO_MATCH_FLOOR == 0.90
