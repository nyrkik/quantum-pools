"""Invoice list search — matches customer name, not just invoice fields.

FB-44 regression guard. Users typing "slate" on /invoices expect to
find Slate Creek's estimates, but the search was limited to
``Invoice.invoice_number`` and ``Invoice.subject``. This test locks
in the outer-join-to-Customer search + the four name fields that
feed it (first_name, last_name, company_name, billing_name).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from src.models.customer import Customer
from src.models.invoice import Invoice
from src.services.invoice_service import InvoiceService


async def _seed_customer(db, org_id: str, **overrides) -> Customer:
    base = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "company_name": None,
    }
    base.update(overrides)
    c = Customer(**base)
    db.add(c)
    await db.flush()
    return c


async def _seed_invoice(
    db, org_id: str, *, customer_id: str | None, **overrides,
) -> Invoice:
    base = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "customer_id": customer_id,
        "invoice_number": f"EST-{uuid.uuid4().hex[:6].upper()}",
        "document_type": "estimate",
        "status": "draft",
        "subject": "Pool timer repair",
        "issue_date": date.today(),
    }
    base.update(overrides)
    i = Invoice(**base)
    db.add(i)
    await db.flush()
    return i


@pytest.mark.asyncio
async def test_search_matches_customer_first_name(db_session, org_a):
    # The real-world pattern — customer lives in `first_name`, which
    # for some orgs holds the whole business name.
    c = await _seed_customer(
        db_session, org_a.id, first_name="Slate Creek Apartments",
    )
    await _seed_invoice(db_session, org_a.id, customer_id=c.id)
    # A red-herring invoice that should NOT match.
    other = await _seed_customer(
        db_session, org_a.id, first_name="Someone Else",
    )
    await _seed_invoice(db_session, org_a.id, customer_id=other.id)
    await db_session.commit()

    invoices, total = await InvoiceService(db_session).list(
        org_a.id, search="slate",
    )
    assert total == 1
    assert invoices[0].customer_id == c.id


@pytest.mark.asyncio
async def test_search_matches_company_name(db_session, org_a):
    c = await _seed_customer(
        db_session, org_a.id,
        first_name="Ashley", last_name="Overton",
        company_name="AIR Communities",
    )
    await _seed_invoice(db_session, org_a.id, customer_id=c.id)
    await db_session.commit()

    _, total = await InvoiceService(db_session).list(org_a.id, search="AIR")
    assert total == 1


@pytest.mark.asyncio
async def test_search_matches_billing_name_on_non_db_customer(db_session, org_a):
    """Non-DB-customer invoices carry ``billing_name``; the search
    must hit that field too — otherwise a manually-billed invoice is
    invisible to the client-name search."""
    await _seed_invoice(
        db_session, org_a.id,
        customer_id=None,
        billing_name="Larkspur Property Management",
        invoice_number="INV-9001",
        document_type="invoice",
    )
    await db_session.commit()

    _, total = await InvoiceService(db_session).list(
        org_a.id, search="larkspur", document_type="invoice",
    )
    assert total == 1


@pytest.mark.asyncio
async def test_search_still_matches_invoice_number_and_subject(db_session, org_a):
    """Regression guard for the pre-fix behavior — these two fields
    must keep working."""
    c = await _seed_customer(db_session, org_a.id, first_name="Unrelated")
    await _seed_invoice(
        db_session, org_a.id, customer_id=c.id,
        invoice_number="EST-26016", subject="Office Spa Timer Repair",
    )
    await db_session.commit()

    svc = InvoiceService(db_session)
    _, by_number = await svc.list(org_a.id, search="26016")
    _, by_subject = await svc.list(org_a.id, search="spa timer")
    assert by_number == 1
    assert by_subject == 1
