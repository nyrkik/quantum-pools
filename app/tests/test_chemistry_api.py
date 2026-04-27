"""Tests for /v1/chemistry endpoints — Phase 3d.2 step 2.

Smoke + behavior tests for the LSI + dosing calculator endpoints.
The router is a thin shell over pure functions (already tested in
test_lsi_calculator.py); this file focuses on:

- Org scoping: 404 for cross-org bow_id
- 404 when no readings exist for /lsi
- 422 when latest reading is missing pH/Ca/alk
- /dosing happy path with full + partial inputs
- /dosing returns null lsi when not enough fields supplied
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.api.deps import OrgUserContext
from src.api.v1.chemistry import (
    DosingRequest,
    calculate_dosing_endpoint,
    get_lsi,
    router as chemistry_router,
)
from src.models.chemical_reading import ChemicalReading
from src.models.customer import Customer
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.permission import Permission
from src.models.property import Property
from src.models.user import User
from src.models.water_feature import WaterFeature


def test_router_paths_registered():
    paths = {r.path for r in chemistry_router.routes}
    assert "/chemistry/water-features/{bow_id}/lsi" in paths
    assert "/chemistry/water-features/{bow_id}/dosing" in paths


async def _seed_user(db, org_id: str, role: OrgRole = OrgRole.owner) -> OrgUserContext:
    """Create a user + org membership + the chemicals.view permission
    grant via the owner preset (which gets it by default in seed)."""
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"chem-{uid[:8]}@t.com",
        hashed_password="x", first_name="Chem", last_name="Tester",
        is_active=True,
    ))
    org_user = OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_id, user_id=uid, role=role,
    )
    db.add(org_user)
    # Ensure the permission row exists so require_permissions can find it.
    db.add(Permission(
        id=str(uuid.uuid4()),
        slug="chemicals.view",
        resource="chemicals",
        action="view",
        description="View chemical readings",
    ))
    await db.flush()
    user = await db.get(User, uid)
    return OrgUserContext(user=user, org_user=org_user, org_name="Test")


async def _seed_bow(db, org_id: str, gallons: int = 20000) -> tuple[str, str]:
    """Customer → Property → WaterFeature, all scoped to org.
    Returns (bow_id, property_id) so callers can attach readings."""
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        first_name="Chem", last_name="Bow",
    )
    db.add(customer)
    await db.flush()
    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        customer_id=customer.id,
        address="1 Test Ln", city="Sac", state="CA", zip_code="95814",
    )
    db.add(prop)
    await db.flush()
    bow = WaterFeature(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        property_id=prop.id,
        water_type="pool",
        pool_gallons=gallons,
    )
    db.add(bow)
    await db.flush()
    return bow.id, prop.id


# ---------------------------------------------------------------------------
# /lsi
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lsi_404_when_no_readings(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    bow_id, prop_id = await _seed_bow(db_session, org_a.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        await get_lsi(bow_id=bow_id, ctx=ctx, db=db_session)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_lsi_404_for_cross_org_bow(db_session, org_a, org_b):
    ctx_a = await _seed_user(db_session, org_a.id)
    bow_b, _ = await _seed_bow(db_session, org_b.id)  # belongs to other org
    await db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        await get_lsi(bow_id=bow_b, ctx=ctx_a, db=db_session)
    assert excinfo.value.status_code == 404  # don't leak existence


@pytest.mark.asyncio
async def test_lsi_422_when_required_field_missing(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    bow_id, prop_id = await _seed_bow(db_session, org_a.id)
    db_session.add(ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=prop_id,
        water_feature_id=bow_id,
        ph=7.4,  # OK
        # calcium_hardness missing
        alkalinity=100,
    ))
    await db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        await get_lsi(bow_id=bow_id, ctx=ctx, db=db_session)
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_lsi_happy_path(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    bow_id, prop_id = await _seed_bow(db_session, org_a.id)
    reading_id = str(uuid.uuid4())
    db_session.add(ChemicalReading(
        id=reading_id,
        organization_id=org_a.id,
        property_id=prop_id,
        water_feature_id=bow_id,
        ph=7.4, calcium_hardness=250, alkalinity=100, cyanuric_acid=30,
    ))
    await db_session.commit()

    out = await get_lsi(bow_id=bow_id, ctx=ctx, db=db_session)
    assert out["classification"] == "balanced"
    assert out["based_on"]["temp_f"] == 75.0
    assert out["based_on"]["ph"] == 7.4
    assert out["reading_id"] == reading_id
    assert out["taken_at"] is not None


# ---------------------------------------------------------------------------
# /dosing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dosing_404_for_cross_org_bow(db_session, org_a, org_b):
    ctx_a = await _seed_user(db_session, org_a.id)
    bow_b, _ = await _seed_bow(db_session, org_b.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        await calculate_dosing_endpoint(
            bow_id=bow_b,
            body=DosingRequest(pool_gallons=20000, ph=7.4),
            ctx=ctx_a,
            db=db_session,
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_dosing_422_for_invalid_gallons(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    bow_id, prop_id = await _seed_bow(db_session, org_a.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        await calculate_dosing_endpoint(
            bow_id=bow_id,
            body=DosingRequest(pool_gallons=0, ph=7.4),
            ctx=ctx,
            db=db_session,
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_dosing_returns_recommendations_and_lsi(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    bow_id, prop_id = await _seed_bow(db_session, org_a.id)
    await db_session.commit()

    out = await calculate_dosing_endpoint(
        bow_id=bow_id,
        body=DosingRequest(
            pool_gallons=20000,
            ph=7.4,
            free_chlorine=2.0,
            alkalinity=100,
            calcium_hardness=250,
            cyanuric_acid=30,
        ),
        ctx=ctx,
        db=db_session,
    )
    assert out["pool_gallons"] == 20000
    assert isinstance(out["dosing"], list)
    assert out["lsi"] is not None
    assert out["lsi"]["classification"] == "balanced"


@pytest.mark.asyncio
async def test_dosing_lsi_null_when_insufficient_inputs(db_session, org_a):
    """LSI requires pH + Ca + alk. Missing any one => null lsi (still
    returns the dosing recommendations for whatever was supplied)."""
    ctx = await _seed_user(db_session, org_a.id)
    bow_id, prop_id = await _seed_bow(db_session, org_a.id)
    await db_session.commit()

    out = await calculate_dosing_endpoint(
        bow_id=bow_id,
        body=DosingRequest(pool_gallons=20000, ph=7.4),  # no Ca, no alk
        ctx=ctx,
        db=db_session,
    )
    assert out["lsi"] is None
    assert isinstance(out["dosing"], list)
