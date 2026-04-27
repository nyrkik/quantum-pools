"""Tests for /v1/reconciliation endpoints — Phase 1 step 6.

Direct-call tests (matching the project's existing API test pattern)
exercise the full action paths: mark-received, manual-match, dismiss.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.api.deps import OrgUserContext
from src.api.v1.reconciliation import (
    ManualMatchBody,
    dismiss_parsed,
    list_needs_review,
    list_pending_checks,
    list_unmatched,
    manual_match,
    mark_payment_received,
    router as reconciliation_router,
)
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.invoice import Invoice, InvoiceStatus
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.parsed_payment import ParsedPayment, ParsedPaymentStatus
from src.models.payment import Payment, PaymentStatus
from src.models.permission import Permission
from src.models.user import User


def test_router_paths_registered():
    paths = {r.path for r in reconciliation_router.routes}
    assert "/reconciliation/pending-checks" in paths
    assert "/reconciliation/needs-review" in paths
    assert "/reconciliation/unmatched" in paths
    assert "/reconciliation/recent-auto-matches" in paths
    assert "/reconciliation/payments/{payment_id}/mark-received" in paths
    assert "/reconciliation/parsed/{parsed_id}/match" in paths
    assert "/reconciliation/parsed/{parsed_id}/dismiss" in paths


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


async def _seed_user(db, org_id: str, role: OrgRole = OrgRole.owner) -> OrgUserContext:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"recon-{uid[:8]}@t.com",
        hashed_password="x", first_name="R", last_name="C", is_active=True,
    ))
    org_user = OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_id, user_id=uid, role=role,
    )
    db.add(org_user)
    db.add(Permission(
        id=str(uuid.uuid4()),
        slug="invoices.create", resource="invoices", action="create",
        description="Create invoices",
    ))
    await db.flush()
    user = await db.get(User, uid)
    return OrgUserContext(user=user, org_user=org_user, org_name="Test")


async def _seed_customer(db, org_id: str, *, balance: float = 0.0) -> Customer:
    c = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        first_name="Pat", last_name="Manager",
        company_name="Test PM Inc",
        balance=balance,
    )
    db.add(c)
    await db.flush()
    return c


async def _seed_invoice(db, org_id: str, customer_id: str, *,
                       total: float = 500.00,
                       status: str = InvoiceStatus.sent.value) -> Invoice:
    inv = Invoice(
        id=str(uuid.uuid4()),
        organization_id=org_id, customer_id=customer_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        status=status,
        issue_date=date.today(),
        subtotal=total, total=total, balance=total, amount_paid=0.0,
    )
    db.add(inv)
    await db.flush()
    return inv


async def _seed_message(db, org_id: str) -> AgentMessage:
    thread = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"recon-{uuid.uuid4().hex[:8]}",
        contact_email="payer@example.com",
        subject="Payment", status="pending", category="billing",
        message_count=1, last_direction="inbound",
    )
    db.add(thread)
    await db.flush()
    msg = AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id, direction="inbound",
        from_email="system@entrata.com", to_email="contact@x.com",
        subject="Payment Submitted", body="...",
        category="billing", status="pending",
        thread_id=thread.id,
    )
    db.add(msg)
    await db.flush()
    return msg


# ---------------------------------------------------------------------------
# mark-received
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_received_flips_pending_to_completed(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_invoice(db_session, org_a.id, cust.id, total=499.00)
    payment = Payment(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=cust.id, invoice_id=inv.id,
        amount=499.00, payment_method="check",
        payment_date=date.today(), status=PaymentStatus.pending.value,
    )
    db_session.add(payment)
    await db_session.commit()

    out = await mark_payment_received(payment_id=payment.id, ctx=ctx, db=db_session)
    assert out["status"] == PaymentStatus.completed.value

    refreshed = await db_session.get(Payment, payment.id)
    assert refreshed.status == PaymentStatus.completed.value
    refreshed_inv = await db_session.get(Invoice, inv.id)
    assert refreshed_inv.status == InvoiceStatus.paid.value


@pytest.mark.asyncio
async def test_mark_received_idempotent_on_completed(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    payment = Payment(
        id=str(uuid.uuid4()),
        organization_id=org_a.id, customer_id=cust.id,
        amount=100.00, payment_method="ach",
        payment_date=date.today(), status=PaymentStatus.completed.value,
    )
    db_session.add(payment)
    await db_session.commit()

    out = await mark_payment_received(payment_id=payment.id, ctx=ctx, db=db_session)
    assert out["status"] == PaymentStatus.completed.value


@pytest.mark.asyncio
async def test_mark_received_404_for_unknown_id(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await mark_payment_received(payment_id=str(uuid.uuid4()), ctx=ctx, db=db_session)
    assert e.value.status_code == 404


# ---------------------------------------------------------------------------
# manual-match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_match_creates_payment_and_terminates_parsed(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_invoice(db_session, org_a.id, cust.id, total=300.00)
    msg = await _seed_message(db_session, org_a.id)
    pp = ParsedPayment(
        id=str(uuid.uuid4()),
        organization_id=org_a.id, agent_message_id=msg.id,
        processor="entrata",
        amount=Decimal("300.00"), payer_name="Test PM Inc",
        payment_method="ach", payment_date=date.today(),
        match_status=ParsedPaymentStatus.unmatched.value,
    )
    db_session.add(pp)
    await db_session.commit()

    out = await manual_match(
        parsed_id=pp.id,
        body=ManualMatchBody(invoice_id=inv.id),
        ctx=ctx, db=db_session,
    )
    assert out["payment_id"] is not None
    assert out["status"] == PaymentStatus.completed.value

    refreshed_pp = await db_session.get(ParsedPayment, pp.id)
    assert refreshed_pp.match_status == ParsedPaymentStatus.manual_matched.value
    assert refreshed_pp.payment_id == out["payment_id"]
    assert refreshed_pp.matched_invoice_id == inv.id


@pytest.mark.asyncio
async def test_manual_match_409_on_terminal_status(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_invoice(db_session, org_a.id, cust.id, total=300.00)
    msg = await _seed_message(db_session, org_a.id)
    pp = ParsedPayment(
        id=str(uuid.uuid4()),
        organization_id=org_a.id, agent_message_id=msg.id,
        processor="entrata", amount=Decimal("300.00"),
        match_status=ParsedPaymentStatus.auto_matched.value,
    )
    db_session.add(pp)
    await db_session.commit()

    with pytest.raises(HTTPException) as e:
        await manual_match(
            parsed_id=pp.id,
            body=ManualMatchBody(invoice_id=inv.id),
            ctx=ctx, db=db_session,
        )
    assert e.value.status_code == 409


# ---------------------------------------------------------------------------
# dismiss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_unmatched_marks_ignored(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    msg = await _seed_message(db_session, org_a.id)
    pp = ParsedPayment(
        id=str(uuid.uuid4()),
        organization_id=org_a.id, agent_message_id=msg.id,
        processor="entrata", amount=Decimal("75.00"),
        match_status=ParsedPaymentStatus.unmatched.value,
    )
    db_session.add(pp)
    await db_session.commit()

    out = await dismiss_parsed(parsed_id=pp.id, ctx=ctx, db=db_session)
    assert out["match_status"] == ParsedPaymentStatus.ignored.value

    refreshed = await db_session.get(ParsedPayment, pp.id)
    assert refreshed.match_status == ParsedPaymentStatus.ignored.value


# ---------------------------------------------------------------------------
# Smoke list endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_endpoints_empty_states(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()
    pending = await list_pending_checks(ctx=ctx, db=db_session)
    needs = await list_needs_review(ctx=ctx, db=db_session)
    unmatched = await list_unmatched(ctx=ctx, db=db_session)
    assert pending == {"items": []}
    assert needs == {"items": []}
    assert unmatched == {"items": []}
