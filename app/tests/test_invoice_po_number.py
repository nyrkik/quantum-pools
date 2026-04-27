"""Tests for PATCH /v1/invoices/{id}/po-number — FB-56.

The endpoint must update only po_number. Approval state, revision_count,
status, approval_id all stay untouched — this was the whole point of
the feedback (don't force a re-approve cycle just to record a PO#).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from src.api.deps import OrgUserContext
from src.api.v1.invoices import POBody, patch_po_number
from src.models.customer import Customer
from src.models.invoice import Invoice, InvoiceStatus
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.user import User


async def _seed_user(db, org_id: str) -> OrgUserContext:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"po-{uid[:8]}@t.com",
        hashed_password="x", first_name="P", last_name="O", is_active=True,
    ))
    org_user = OrganizationUser(
        id=str(uuid.uuid4()), organization_id=org_id, user_id=uid, role=OrgRole.owner,
    )
    db.add(org_user)
    await db.flush()
    user = await db.get(User, uid)
    return OrgUserContext(user=user, org_user=org_user, org_name="Test")


async def _seed_customer(db, org_id: str) -> Customer:
    c = Customer(
        id=str(uuid.uuid4()), organization_id=org_id,
        first_name="P", last_name="M", company_name="Test PM",
    )
    db.add(c)
    await db.flush()
    return c


async def _seed_approved_estimate(db, org_id: str, customer_id: str) -> Invoice:
    """Approved estimate — has approval timestamp, status=approved,
    revision_count=0. The endpoint must preserve all of these."""
    inv = Invoice(
        id=str(uuid.uuid4()), organization_id=org_id, customer_id=customer_id,
        document_type="estimate", status="approved",
        invoice_number=f"EST-{uuid.uuid4().hex[:6]}",
        issue_date=date.today(),
        subtotal=500.00, total=500.00, balance=500.00,
        approved_at=datetime(2026, 4, 20, 14, 30, tzinfo=timezone.utc),
        approved_by="Sierra Oaks - K. Manager",
        revision_count=0,
    )
    db.add(inv)
    await db.flush()
    return inv


# ---------------------------------------------------------------------------
# Happy path: set + clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_po_number_preserves_approval_state(db_session, org_a):
    """The crux of FB-56: setting a PO# on an approved estimate must
    leave approved_at, approved_by, status, revision_count untouched."""
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_approved_estimate(db_session, org_a.id, cust.id)
    original_approved_at = inv.approved_at
    original_approved_by = inv.approved_by
    original_status = inv.status
    original_rev = inv.revision_count
    await db_session.commit()

    out = await patch_po_number(
        invoice_id=inv.id,
        body=POBody(po_number="PO-12345"),
        ctx=ctx, db=db_session,
    )
    assert out["po_number"] == "PO-12345"

    refreshed = await db_session.get(Invoice, inv.id)
    assert refreshed.po_number == "PO-12345"
    # All approval-state fields untouched.
    assert refreshed.approved_at == original_approved_at
    assert refreshed.approved_by == original_approved_by
    assert refreshed.status == original_status
    assert refreshed.revision_count == original_rev


@pytest.mark.asyncio
async def test_clearing_po_number(db_session, org_a):
    """Empty string or null clears the field."""
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_approved_estimate(db_session, org_a.id, cust.id)
    inv.po_number = "PO-OLD"
    await db_session.commit()

    out = await patch_po_number(
        invoice_id=inv.id, body=POBody(po_number=None), ctx=ctx, db=db_session,
    )
    assert out["po_number"] is None

    out2 = await patch_po_number(
        invoice_id=inv.id, body=POBody(po_number=""), ctx=ctx, db=db_session,
    )
    assert out2["po_number"] is None


@pytest.mark.asyncio
async def test_whitespace_trimmed(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_approved_estimate(db_session, org_a.id, cust.id)
    await db_session.commit()
    out = await patch_po_number(
        invoice_id=inv.id, body=POBody(po_number="  PO-555  "),
        ctx=ctx, db=db_session,
    )
    assert out["po_number"] == "PO-555"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_on_unknown_invoice(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await patch_po_number(
            invoice_id=str(uuid.uuid4()),
            body=POBody(po_number="PO-1"), ctx=ctx, db=db_session,
        )
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_404_on_cross_org_invoice(db_session, org_a, org_b):
    """Don't leak existence — return 404 for another org's invoice."""
    ctx_a = await _seed_user(db_session, org_a.id)
    cust_b = await _seed_customer(db_session, org_b.id)
    inv_b = await _seed_approved_estimate(db_session, org_b.id, cust_b.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await patch_po_number(
            invoice_id=inv_b.id,
            body=POBody(po_number="PO-X"), ctx=ctx_a, db=db_session,
        )
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_422_on_oversized_po_number(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = await _seed_approved_estimate(db_session, org_a.id, cust.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await patch_po_number(
            invoice_id=inv.id,
            body=POBody(po_number="X" * 51),
            ctx=ctx, db=db_session,
        )
    assert e.value.status_code == 422


# ---------------------------------------------------------------------------
# Works regardless of status — PO# is editable always
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_works_on_draft_estimate(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = Invoice(
        id=str(uuid.uuid4()), organization_id=org_a.id, customer_id=cust.id,
        document_type="estimate", status="draft",
        invoice_number=f"EST-{uuid.uuid4().hex[:6]}",
        issue_date=date.today(),
        subtotal=100, total=100, balance=100,
    )
    db_session.add(inv)
    await db_session.commit()
    out = await patch_po_number(
        invoice_id=inv.id, body=POBody(po_number="PO-DRAFT"),
        ctx=ctx, db=db_session,
    )
    assert out["po_number"] == "PO-DRAFT"


@pytest.mark.asyncio
async def test_works_on_paid_invoice(db_session, org_a):
    """Even paid invoices get PO# updates — customer sometimes provides
    it after the fact for their AP system reconciliation."""
    ctx = await _seed_user(db_session, org_a.id)
    cust = await _seed_customer(db_session, org_a.id)
    inv = Invoice(
        id=str(uuid.uuid4()), organization_id=org_a.id, customer_id=cust.id,
        document_type="invoice", status=InvoiceStatus.paid.value,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        issue_date=date.today(),
        subtotal=100, total=100, balance=0, amount_paid=100,
        paid_date=date.today(),
    )
    db_session.add(inv)
    await db_session.commit()
    out = await patch_po_number(
        invoice_id=inv.id, body=POBody(po_number="PO-AFTER"),
        ctx=ctx, db=db_session,
    )
    assert out["po_number"] == "PO-AFTER"
    refreshed = await db_session.get(Invoice, inv.id)
    assert refreshed.status == InvoiceStatus.paid.value  # unchanged
