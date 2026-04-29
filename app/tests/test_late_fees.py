"""Phase 8: late-fee tests.

Locks in:
- Org-disabled → no fees applied / preview is empty.
- PSS-imported invoices excluded.
- Customer override (False) excludes a single customer.
- Idempotent: running twice doesn't duplicate the line item.
- Flat vs percent computation, including minimum floor.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from src.models.customer import Customer
from src.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus
from src.services.billing_service import BillingService


def _mk_invoice(
    org_id: str,
    customer_id: str | None,
    *,
    days_past_due: int,
    balance: float = 100.0,
    pss: bool = False,
) -> Invoice:
    today = date.today()
    inv = Invoice(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        customer_id=customer_id,
        document_type="invoice",
        invoice_number=f"TEST-{uuid.uuid4().hex[:6]}",
        status=InvoiceStatus.sent.value,
        issue_date=today - timedelta(days=days_past_due + 30),
        due_date=today - timedelta(days=days_past_due),
        subtotal=balance,
        total=balance,
        balance=balance,
        pss_invoice_id="pss-123" if pss else None,
    )
    # Mirror real-world invoices — InvoiceService always creates line
    # items, and run_late_fees recomputes totals from those items.
    inv.line_items = [
        InvoiceLineItem(
            id=str(uuid.uuid4()),
            invoice_id=inv.id,
            description="Pool service",
            quantity=1.0,
            unit_price=balance,
            amount=balance,
            is_taxed=False,
            sort_order=0,
        )
    ]
    return inv


def _enable_late_fees(org, *, type_="flat", amount=25.0, grace=30, minimum=None):
    org.late_fee_enabled = True
    org.late_fee_type = type_
    org.late_fee_amount = amount
    org.late_fee_grace_days = grace
    org.late_fee_minimum = minimum


@pytest.mark.asyncio
async def test_disabled_returns_empty_preview(db_session, org_a):
    bsvc = BillingService(db_session)
    out = await bsvc.preview_late_fees(org_a.id)
    assert out["enabled"] is False
    assert out["would_apply_count"] == 0


@pytest.mark.asyncio
async def test_flat_fee_applied_idempotently(db_session, org_a):
    _enable_late_fees(org_a, type_="flat", amount=25.0, grace=30)
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Late",
        last_name="Customer",
    )
    db_session.add(customer)
    inv = _mk_invoice(org_a.id, customer.id, days_past_due=45, balance=200.0)
    db_session.add(inv)
    await db_session.commit()

    bsvc = BillingService(db_session)
    out1 = await bsvc.run_late_fees(org_a.id)
    assert out1["applied"] == 1
    await db_session.refresh(inv)
    # 200 + 25 fee = 225
    assert round(inv.total, 2) == 225.00

    # Direct DB check — was the late-fee line item persisted?
    from sqlalchemy import select as _s
    items = (await db_session.execute(
        _s(InvoiceLineItem).where(InvoiceLineItem.invoice_id == inv.id)
    )).scalars().all()
    descs = [li.description for li in items]
    assert any(d.startswith("Late fee") for d in descs), (
        f"Expected a 'Late fee' line item, got {descs}"
    )

    # Production runs each get a fresh DB session via get_db_context.
    # Mirror that — close and reopen so the second invocation sees a
    # fully-fresh load with the late-fee line item present.
    await db_session.close()
    from tests.conftest import _TestSessionLocal  # type: ignore
    fresh_session = _TestSessionLocal()
    try:
        bsvc2 = BillingService(fresh_session)
        out2 = await bsvc2.run_late_fees(org_a.id)
        assert out2["applied"] == 0
        assert out2["skipped"] == 1
        from sqlalchemy import select as _s2
        items2 = (await fresh_session.execute(
            _s2(InvoiceLineItem).where(InvoiceLineItem.invoice_id == inv.id)
        )).scalars().all()
        # Still only 2 line items (Pool service + 1 Late fee — not 2).
        assert len([li for li in items2 if li.description.startswith("Late fee")]) == 1
    finally:
        await fresh_session.close()


@pytest.mark.asyncio
async def test_percent_with_minimum(db_session, org_a):
    """1.5% on $20 invoice = $0.30, but min=$5 floors it to $5."""
    _enable_late_fees(org_a, type_="percent", amount=1.5, grace=30, minimum=5.0)
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Small",
        last_name="Customer",
    )
    db_session.add(customer)
    inv = _mk_invoice(org_a.id, customer.id, days_past_due=45, balance=20.0)
    db_session.add(inv)
    await db_session.commit()

    bsvc = BillingService(db_session)
    out = await bsvc.run_late_fees(org_a.id)
    assert out["applied"] == 1
    await db_session.refresh(inv)
    # 20 + 5 (min floor) = 25
    assert round(inv.total, 2) == 25.00


@pytest.mark.asyncio
async def test_pss_invoices_excluded(db_session, org_a):
    _enable_late_fees(org_a, type_="flat", amount=25.0, grace=30)
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="PSS",
        last_name="Customer",
    )
    db_session.add(customer)
    inv = _mk_invoice(org_a.id, customer.id, days_past_due=45, pss=True)
    db_session.add(inv)
    await db_session.commit()

    bsvc = BillingService(db_session)
    preview = await bsvc.preview_late_fees(org_a.id)
    assert preview["would_apply_count"] == 0
    out = await bsvc.run_late_fees(org_a.id)
    assert out["applied"] == 0


@pytest.mark.asyncio
async def test_customer_override_excludes(db_session, org_a):
    _enable_late_fees(org_a, type_="flat", amount=25.0, grace=30)
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="OptOut",
        last_name="Customer",
        late_fee_override_enabled=False,  # explicit opt-out
    )
    db_session.add(customer)
    inv = _mk_invoice(org_a.id, customer.id, days_past_due=45)
    db_session.add(inv)
    await db_session.commit()

    bsvc = BillingService(db_session)
    out = await bsvc.run_late_fees(org_a.id)
    assert out["applied"] == 0
    assert out["skipped"] == 1


@pytest.mark.asyncio
async def test_under_grace_skipped(db_session, org_a):
    _enable_late_fees(org_a, type_="flat", amount=25.0, grace=30)
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Recent",
        last_name="Customer",
    )
    db_session.add(customer)
    # Only 10 days past due, grace is 30 → not eligible
    inv = _mk_invoice(org_a.id, customer.id, days_past_due=10)
    db_session.add(inv)
    await db_session.commit()

    bsvc = BillingService(db_session)
    out = await bsvc.run_late_fees(org_a.id)
    assert out["applied"] == 0
    assert out["skipped"] == 1
