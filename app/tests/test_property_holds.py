"""Phase 8: property service-hold tests.

Two contracts to lock in:
1. The `is_property_held` predicate honors inclusive boundary dates.
2. `BillingService._all_properties_held` returns True iff EVERY active
   property is on a hold covering the given date — single-property
   customers skip cleanly, multi-property partial-hold scenarios still bill.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from src.models.customer import Customer
from src.models.property import Property
from src.models.property_hold import PropertyHold
from src.services.billing_service import BillingService
from src.services.property_hold_service import PropertyHoldService


@pytest.mark.asyncio
async def test_is_property_held_inclusive_boundaries(db_session, org_a):
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Test",
        last_name="Customer",
    )
    db_session.add(customer)
    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=customer.id,
        address="1 Test Ln",
        city="Test",
        state="CA",
        zip_code="00000",
    )
    db_session.add(prop)
    await db_session.commit()

    svc = PropertyHoldService(db_session)
    today = date.today()
    await svc.create(
        org_id=org_a.id,
        property_id=prop.id,
        start_date=today,
        end_date=today + timedelta(days=10),
        reason="winterized",
    )
    await db_session.commit()

    # Inside, on start, on end → True. Day before / day after → False.
    assert await svc.is_property_held(prop.id, today)
    assert await svc.is_property_held(prop.id, today + timedelta(days=10))
    assert await svc.is_property_held(prop.id, today + timedelta(days=5))
    assert not await svc.is_property_held(prop.id, today - timedelta(days=1))
    assert not await svc.is_property_held(prop.id, today + timedelta(days=11))


@pytest.mark.asyncio
async def test_create_rejects_inverted_dates(db_session, org_a):
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Test",
        last_name="Customer",
    )
    db_session.add(customer)
    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=customer.id,
        address="2 Test Ln",
        city="Test",
        state="CA",
        zip_code="00000",
    )
    db_session.add(prop)
    await db_session.commit()

    svc = PropertyHoldService(db_session)
    from src.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        await svc.create(
            org_id=org_a.id,
            property_id=prop.id,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 5, 1),
        )


@pytest.mark.asyncio
async def test_all_properties_held_single_property(db_session, org_a):
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Solo",
        last_name="Customer",
    )
    db_session.add(customer)
    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=customer.id,
        address="1 Solo Ln",
        city="X",
        state="CA",
        zip_code="00000",
        is_active=True,
    )
    db_session.add(prop)
    await db_session.commit()

    bsvc = BillingService(db_session)
    today = date.today()
    assert not await bsvc._all_properties_held(customer.id, today)

    db_session.add(
        PropertyHold(
            id=str(uuid.uuid4()),
            property_id=prop.id,
            organization_id=org_a.id,
            start_date=today,
            end_date=today + timedelta(days=30),
        )
    )
    await db_session.commit()
    assert await bsvc._all_properties_held(customer.id, today)


@pytest.mark.asyncio
async def test_all_properties_held_partial_multi(db_session, org_a):
    """Customer with 2 properties, only 1 held → must NOT skip billing."""
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Multi",
        last_name="Customer",
    )
    db_session.add(customer)
    p1 = Property(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=customer.id,
        address="1 Multi Ln",
        city="X",
        state="CA",
        zip_code="00000",
        is_active=True,
    )
    p2 = Property(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=customer.id,
        address="2 Multi Ln",
        city="X",
        state="CA",
        zip_code="00000",
        is_active=True,
    )
    db_session.add_all([p1, p2])
    today = date.today()
    db_session.add(
        PropertyHold(
            id=str(uuid.uuid4()),
            property_id=p1.id,
            organization_id=org_a.id,
            start_date=today,
            end_date=today + timedelta(days=30),
        )
    )
    await db_session.commit()

    bsvc = BillingService(db_session)
    assert not await bsvc._all_properties_held(customer.id, today)

    # Hold the second one too → now skip
    db_session.add(
        PropertyHold(
            id=str(uuid.uuid4()),
            property_id=p2.id,
            organization_id=org_a.id,
            start_date=today,
            end_date=today + timedelta(days=30),
        )
    )
    await db_session.commit()
    assert await bsvc._all_properties_held(customer.id, today)


@pytest.mark.asyncio
async def test_all_properties_held_no_properties(db_session, org_a):
    """Customer with no properties → False (let billing proceed)."""
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Empty",
        last_name="Customer",
    )
    db_session.add(customer)
    await db_session.commit()
    bsvc = BillingService(db_session)
    assert not await bsvc._all_properties_held(customer.id, date.today())
