"""Tests the brand authority list + sync override behavior.

This guards the regression we hit on 2026-04-26: the EMD PDF extractor
sometimes drops sanitizer-feeder brands (Rolachem, Stenner, Pulsar, etc.)
into `filter_pump_*` fields. v1 of the equipment-from-inspections sync
faithfully created `equipment_type='pump'` rows from those wrong fields.
The fix is a brand-authority override that coerces `equipment_type` to
the brand's canonical category, regardless of which slot the PDF parsed
it into.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.models.customer import Customer
from src.models.equipment_item import EquipmentItem
from src.models.inspection import Inspection
from src.models.inspection_equipment import InspectionEquipment
from src.models.inspection_facility import InspectionFacility
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.services.equipment.brand_authority import authoritative_type
from src.services.inspection.service import InspectionService

pytestmark = pytest.mark.asyncio


def test_authoritative_type_recognizes_known_brands():
    assert authoritative_type("Rolachem") == "sanitizer"
    assert authoritative_type("ROLACHEM") == "sanitizer"
    assert authoritative_type("rolachem") == "sanitizer"
    assert authoritative_type("rola-chem") == "sanitizer"
    assert authoritative_type("Stenner") == "sanitizer"
    assert authoritative_type("Blue-White") == "sanitizer"
    assert authoritative_type("Pulsar") == "sanitizer"


def test_authoritative_type_handles_extra_text_around_brand():
    """`Rolachem auto feeder` / `Rolachem RC103SC` should still match."""
    assert authoritative_type("Rolachem auto feeder") == "sanitizer"
    assert authoritative_type("Rolachem RC103SC") == "sanitizer"


def test_authoritative_type_rejects_short_noisy_inputs():
    """Single letters / very short strings (separate PDF-extractor bug) must NOT match."""
    assert authoritative_type("P") is None    # could be Pentair, ProMinent, Pulsar — too ambiguous
    assert authoritative_type("S") is None
    assert authoritative_type("H") is None
    assert authoritative_type("Rol") is None  # only 3 chars — under threshold
    assert authoritative_type("") is None
    assert authoritative_type(None) is None


def test_authoritative_type_returns_none_for_pump_brands():
    """Brands that are explicitly NOT in the authority list should return None."""
    assert authoritative_type("Pentair") is None
    assert authoritative_type("Hayward") is None
    assert authoritative_type("Sta-Rite") is None
    assert authoritative_type("Aquastar") is None


async def _seed_minimal_facility(db, org):
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        first_name="X",
        last_name="Y",
    )
    db.add(customer)
    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        customer_id=customer.id,
        address="1 Pool Way",
        city="Sacramento",
        state="CA",
        zip_code="95814",
    )
    db.add(prop)
    wf = WaterFeature(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        property_id=prop.id,
        water_type="pool",
    )
    db.add(wf)
    facility = InspectionFacility(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name="Test",
        street_address="1 Pool Way",
        matched_property_id=prop.id,
        matched_at=datetime.now(timezone.utc),
    )
    db.add(facility)
    await db.flush()
    inspection = Inspection(id=str(uuid.uuid4()), facility_id=facility.id)
    db.add(inspection)
    await db.flush()
    return prop, wf, facility, inspection


async def test_sync_overrides_brand_authority_to_sanitizer(db_session, org_a):
    """Rolachem in filter_pump_2 slot must produce a sanitizer row, not a pump row."""
    prop, wf, facility, inspection = await _seed_minimal_facility(db_session, org_a)
    ie = InspectionEquipment(
        id=str(uuid.uuid4()),
        inspection_id=inspection.id,
        facility_id=facility.id,
        # Real pump in slot 1
        filter_pump_1_make="Pentair",
        filter_pump_1_model="WhisperFlo",
        # Sanitizer brand misrouted into slot 2 by the PDF extractor
        filter_pump_2_make="Rolachem",
        filter_pump_2_model="RC103SC",
    )
    db_session.add(ie)
    await db_session.flush()

    svc = InspectionService(db_session)
    result = await svc.sync_equipment_to_bow(facility.id)
    assert result is not None

    rows = (await db_session.execute(
        select(EquipmentItem).where(EquipmentItem.water_feature_id == wf.id)
    )).scalars().all()

    # Find the Rolachem row
    rolachem_rows = [r for r in rows if (r.brand or "").lower() == "rolachem"]
    assert len(rolachem_rows) == 1
    rolachem = rolachem_rows[0]
    assert rolachem.equipment_type == "sanitizer", (
        f"brand authority override should have flipped Rolachem to sanitizer, "
        f"got {rolachem.equipment_type}"
    )
    assert rolachem.system_group is None  # cleared by override

    # Pentair WhisperFlo stays as a pump (no authority override)
    pentair_rows = [r for r in rows if (r.brand or "").lower() == "pentair"]
    assert len(pentair_rows) == 1
    assert pentair_rows[0].equipment_type == "pump"


async def test_sync_skips_double_capture_when_sanitizer_slot_has_same_entity(db_session, org_a):
    """If sanitizer_1 already captures Rolachem, the misrouted filter_pump_2 entry
    must be skipped — same physical entity, double-captured by the PDF extractor."""
    prop, wf, facility, inspection = await _seed_minimal_facility(db_session, org_a)
    ie = InspectionEquipment(
        id=str(uuid.uuid4()),
        inspection_id=inspection.id,
        facility_id=facility.id,
        filter_pump_2_make="Rolachem",
        filter_pump_2_model="RC103SC",
        sanitizer_1_type="Liquid",
        sanitizer_1_details="Rolachem RC103SC",
    )
    db_session.add(ie)
    await db_session.flush()

    svc = InspectionService(db_session)
    result = await svc.sync_equipment_to_bow(facility.id)
    summary = result["updated_fields"]["equipment_items"]

    # Skipped the double-capture
    assert summary["skipped"] >= 1

    rows = (await db_session.execute(
        select(EquipmentItem).where(
            EquipmentItem.water_feature_id == wf.id,
            EquipmentItem.is_active == True,
        )
    )).scalars().all()

    # Only the sanitizer_1 row, no Rolachem-as-pump row
    assert len(rows) == 1
    assert rows[0].source_slot == "sanitizer_1"
    assert rows[0].equipment_type == "sanitizer"
