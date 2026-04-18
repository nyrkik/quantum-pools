"""Integration tests — chemistry subsystem emits expected events.

Covers Phase 1 Step 6 per docs/ai-platform-phase-1.md §6.7:
- chemical_reading.logged on every reading creation (any source)
- chemistry.reading.out_of_range once per out-of-range parameter
- threshold table behavior (pure unit tests on _check_thresholds)
- source + actor attribution (manual / deepblue / visit)
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.models.chemical_reading import ChemicalReading
from src.services.chemical_service import ChemicalService
from src.services.events.chemistry import (
    OutOfRange,
    _check_thresholds,
    emit_chemical_reading_logged,
    emit_chemistry_out_of_range_events,
)
from src.services.events.platform_event_service import Actor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_property(db_session, org_a):
    """Property + customer for reading-creation tests."""
    from src.models.customer import Customer
    from src.models.property import Property

    cust = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        first_name="Test", last_name="Cust",
        email="t@test.com", customer_type="residential",
    )
    db_session.add(cust)
    await db_session.flush()

    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        customer_id=cust.id,
        address="123 Test St",
        city="Sacramento", state="CA", zip_code="95814",
        pool_gallons=15000,
    )
    db_session.add(prop)
    await db_session.commit()
    return prop


# ---------------------------------------------------------------------------
# Threshold table — pure unit tests (no DB needed)
# ---------------------------------------------------------------------------


class _FakeReading:
    """Minimal stand-in for ChemicalReading for threshold tests."""
    def __init__(self, **kwargs):
        self.ph = None
        self.free_chlorine = None
        self.combined_chlorine = None
        self.alkalinity = None
        self.calcium_hardness = None
        self.cyanuric_acid = None
        self.phosphates = None
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_thresholds_returns_empty_when_everything_in_range():
    r = _FakeReading(ph=7.4, free_chlorine=2.0, alkalinity=100,
                     calcium_hardness=300, cyanuric_acid=40)
    assert _check_thresholds(r) == []


def test_ph_low_warning_and_critical():
    assert _check_thresholds(_FakeReading(ph=7.0)) == [
        OutOfRange("ph", 7.0, "low", "warning", "residential_default"),
    ]
    assert _check_thresholds(_FakeReading(ph=6.5)) == [
        OutOfRange("ph", 6.5, "low", "critical", "residential_default"),
    ]


def test_free_chlorine_low_critical_below_half():
    result = _check_thresholds(_FakeReading(free_chlorine=0.3))
    assert len(result) == 1
    assert result[0].parameter == "free_chlorine"
    assert result[0].severity == "critical"
    assert result[0].direction == "low"


def test_free_chlorine_high_warning():
    result = _check_thresholds(_FakeReading(free_chlorine=6.0))
    assert result[0].severity == "warning"
    assert result[0].direction == "high"


def test_combined_chlorine_high_triggered():
    assert _check_thresholds(_FakeReading(combined_chlorine=0.7))[0].parameter == "combined_chlorine"


def test_multiple_out_of_range_params_all_returned():
    r = _FakeReading(ph=6.5, free_chlorine=0.2, alkalinity=50)
    result = _check_thresholds(r)
    params = {b.parameter for b in result}
    assert params == {"ph", "free_chlorine", "alkalinity"}


def test_unmeasured_parameters_skipped():
    # Only pH provided; others None → no events for them.
    result = _check_thresholds(_FakeReading(ph=7.4))
    assert result == []


# ---------------------------------------------------------------------------
# emit_chemical_reading_logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reading_logged_emits_with_source_and_user_actor(
    db_session, org_a, seeded_property, event_recorder
):
    reading = ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=seeded_property.id,
        ph=7.4,
        free_chlorine=2.0,
    )
    db_session.add(reading)
    await db_session.flush()

    actor = Actor(actor_type="user", user_id="tech-1")
    await emit_chemical_reading_logged(db_session, reading, source="manual", actor=actor)
    await db_session.commit()

    event = await event_recorder.assert_emitted(
        "chemical_reading.logged",
        chemical_reading_id=reading.id,
        property_id=seeded_property.id,
    )
    assert event["level"] == "user_action"
    assert event["actor_user_id"] == "tech-1"
    assert event["payload"]["source"] == "manual"


@pytest.mark.asyncio
async def test_reading_logged_deepblue_source_is_agent_level_when_actor_is_agent(
    db_session, org_a, seeded_property, event_recorder
):
    from src.services.events.actor_factory import actor_agent
    reading = ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=seeded_property.id,
        ph=7.4,
    )
    db_session.add(reading)
    await db_session.flush()

    await emit_chemical_reading_logged(
        db_session, reading, source="test_strip_vision",
        actor=actor_agent("test_strip_extractor"),
    )
    await db_session.commit()

    event = await event_recorder.assert_emitted("chemical_reading.logged")
    assert event["level"] == "agent_action"
    assert event["actor_type"] == "agent"
    assert event["payload"]["source"] == "test_strip_vision"


# ---------------------------------------------------------------------------
# emit_chemistry_out_of_range_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_range_emits_one_event_per_parameter(
    db_session, org_a, seeded_property, event_recorder
):
    reading = ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=seeded_property.id,
        ph=6.5,              # critical low
        free_chlorine=0.3,   # critical low
        alkalinity=50,       # critical low
    )
    db_session.add(reading)
    await db_session.flush()

    count = await emit_chemistry_out_of_range_events(db_session, reading)
    assert count == 3
    await db_session.commit()

    events = await event_recorder.all_of_type("chemistry.reading.out_of_range")
    assert len(events) == 3
    params = sorted(e["payload"]["parameter"] for e in events)
    assert params == ["alkalinity", "free_chlorine", "ph"]
    for e in events:
        assert e["level"] == "system_action"
        assert e["actor_type"] == "system"
        assert e["payload"]["threshold_source"] == "residential_default"
        assert e["payload"]["severity"] in ("warning", "critical", "closure_required")


@pytest.mark.asyncio
async def test_out_of_range_emits_nothing_when_all_in_range(
    db_session, org_a, seeded_property, event_recorder
):
    reading = ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=seeded_property.id,
        ph=7.4, free_chlorine=2.0, alkalinity=100, calcium_hardness=300, cyanuric_acid=40,
    )
    db_session.add(reading)
    await db_session.flush()

    count = await emit_chemistry_out_of_range_events(db_session, reading)
    assert count == 0
    await db_session.commit()
    await event_recorder.assert_not_emitted("chemistry.reading.out_of_range")


# ---------------------------------------------------------------------------
# End-to-end via ChemicalService.create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_create_emits_logged_and_out_of_range_events(
    db_session, org_a, seeded_property, event_recorder
):
    """ChemicalService.create — the /readings endpoint's entry point —
    must emit chemical_reading.logged once AND one out_of_range event
    per threshold breach."""
    actor = Actor(actor_type="user", user_id="tech-1")
    svc = ChemicalService(db_session)
    reading = await svc.create(
        org_a.id,
        property_id=seeded_property.id,
        ph=6.5,            # critical low
        free_chlorine=0.2, # critical low
        alkalinity=100,    # in range
        actor=actor,
        source="manual",
    )
    await db_session.commit()

    # One chemical_reading.logged
    logged = await event_recorder.assert_emitted(
        "chemical_reading.logged", chemical_reading_id=reading.id,
    )
    assert logged["payload"]["source"] == "manual"
    assert logged["actor_user_id"] == "tech-1"

    # Two out_of_range (ph + free_chlorine)
    breach_events = await event_recorder.all_of_type("chemistry.reading.out_of_range")
    assert len(breach_events) == 2


@pytest.mark.asyncio
async def test_service_create_clean_reading_emits_only_logged(
    db_session, org_a, seeded_property, event_recorder
):
    svc = ChemicalService(db_session)
    await svc.create(
        org_a.id,
        property_id=seeded_property.id,
        ph=7.4, free_chlorine=2.0,
        source="manual",
    )
    await db_session.commit()

    logged = await event_recorder.all_of_type("chemical_reading.logged")
    breaches = await event_recorder.all_of_type("chemistry.reading.out_of_range")
    assert len(logged) == 1
    assert len(breaches) == 0


@pytest.mark.asyncio
async def test_reading_event_omits_null_entity_ref_keys(
    db_session, org_a, seeded_property, event_recorder
):
    """entity_refs should only contain populated FK keys — null values
    should be omitted so queries like `entity_refs @> '{water_feature_id:
    X}'` work cleanly and distinct-key enumeration doesn't see noise."""
    # No water_feature_id, no visit_id on this reading
    reading = ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=seeded_property.id,
        ph=7.4,
    )
    db_session.add(reading)
    await db_session.flush()

    await emit_chemical_reading_logged(db_session, reading, source="manual")
    await db_session.commit()

    event = await event_recorder.find("chemical_reading.logged")
    assert event is not None
    assert "water_feature_id" not in event["entity_refs"]
    assert "visit_id" not in event["entity_refs"]
    # Required keys still present
    assert event["entity_refs"]["chemical_reading_id"] == reading.id
    assert event["entity_refs"]["property_id"] == seeded_property.id


@pytest.mark.asyncio
async def test_out_of_range_event_omits_null_water_feature_id(
    db_session, org_a, seeded_property, event_recorder
):
    reading = ChemicalReading(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        property_id=seeded_property.id,
        ph=6.5,  # breach
    )
    db_session.add(reading)
    await db_session.flush()
    await emit_chemistry_out_of_range_events(db_session, reading)
    await db_session.commit()

    events = await event_recorder.all_of_type("chemistry.reading.out_of_range")
    assert len(events) == 1
    assert "water_feature_id" not in events[0]["entity_refs"]


@pytest.mark.asyncio
async def test_service_create_rolls_back_emits_when_business_op_fails(
    db_session, org_a, event_recorder
):
    """If the create raises (e.g. invalid property_id), no events persist —
    emits shared the txn with the insert."""
    svc = ChemicalService(db_session)
    with pytest.raises(Exception):
        await svc.create(
            org_a.id,
            property_id="nonexistent-property-id",  # FK violation
            ph=6.5, free_chlorine=0.2,
            source="manual",
        )
    await db_session.rollback()

    assert (await event_recorder.all_of_type("chemical_reading.logged")) == []
    assert (await event_recorder.all_of_type("chemistry.reading.out_of_range")) == []
