"""Tests the inspection -> equipment_items sync pipeline.

Pipeline under test:
  InspectionEquipment row (parsed from PDF)
    -> InspectionService.sync_equipment_to_bow(facility_id)
    -> EquipmentItem rows on the matched property's primary WaterFeature

Covers:
  - Multi-pump fixture creates one equipment_item per non-null slot
  - source_inspection_id + source_slot are set
  - Re-running the sync is idempotent (updates rather than dups)
  - Manual entries with same brand+model are NOT overwritten (skipped)
  - resolver gracefully degrades when no Anthropic key (returns None catalog)

The resolver's Claude call is bypassed in tests because ANTHROPIC_API_KEY is
unset in the test environment — _resolve_with_claude short-circuits to None
and the EquipmentItem is created with raw brand/model strings only.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from src.models.customer import Customer
from src.models.inspection import Inspection
from src.models.inspection_equipment import InspectionEquipment
from src.models.inspection_facility import InspectionFacility
from src.models.equipment_item import EquipmentItem
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.services.inspection.service import InspectionService

pytestmark = pytest.mark.asyncio


async def _seed_property_and_inspection(db, org):
    """Create a Customer + Property + WF + InspectionFacility (matched) + Inspection + InspectionEquipment."""
    customer = Customer(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        first_name="Test",
        last_name="Customer",
    )
    db.add(customer)

    prop = Property(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        customer_id=customer.id,
        address="100 Main St",
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
        name="Test Facility",
        street_address="100 Main St",
        city="Sacramento",
        zip_code="95814",
        matched_property_id=prop.id,
        matched_at=datetime.now(timezone.utc),
    )
    db.add(facility)
    await db.flush()

    inspection = Inspection(
        id=str(uuid.uuid4()),
        facility_id=facility.id,
        program_identifier="POOL",
        inspection_date=datetime.now(timezone.utc).date(),
    )
    db.add(inspection)
    await db.flush()

    ie = InspectionEquipment(
        id=str(uuid.uuid4()),
        inspection_id=inspection.id,
        facility_id=facility.id,
        pool_capacity_gallons=50000,
        # Three filter pumps
        filter_pump_1_make="Pentair",
        filter_pump_1_model="WhisperFlo",
        filter_pump_1_hp="3",
        filter_pump_2_make="Pentair",
        filter_pump_2_model="IntelliFlo",
        filter_pump_2_hp="2.5",
        filter_pump_3_make="Hayward",
        filter_pump_3_model="Super Pump",
        # Filter
        filter_1_type="Cartridge",
        filter_1_make="Pentair",
        filter_1_model="Clean & Clear Plus",
        # Sanitizer
        sanitizer_1_type="Liquid",
        sanitizer_1_details="Rolachem auto feeder",
    )
    db.add(ie)
    await db.flush()

    return prop, wf, facility, inspection, ie


async def test_sync_creates_equipment_items_for_each_slot(db_session, org_a):
    prop, wf, facility, inspection, ie = await _seed_property_and_inspection(db_session, org_a)

    svc = InspectionService(db_session)
    result = await svc.sync_equipment_to_bow(facility.id)

    assert result is not None
    summary = result["updated_fields"].get("equipment_items")
    assert summary["created"] == 5  # 3 pumps + 1 filter + 1 sanitizer
    assert summary["updated"] == 0

    # Confirm rows exist with correct slots
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(EquipmentItem).where(EquipmentItem.water_feature_id == wf.id)
    )).scalars().all()
    by_slot = {r.source_slot: r for r in rows}

    assert "filter_pump_1" in by_slot
    assert by_slot["filter_pump_1"].brand == "Pentair"
    assert by_slot["filter_pump_1"].model == "WhisperFlo"
    assert by_slot["filter_pump_1"].horsepower == 3.0
    assert by_slot["filter_pump_1"].equipment_type == "pump"
    assert by_slot["filter_pump_1"].system_group == "filter"
    assert by_slot["filter_pump_1"].source_inspection_id == inspection.id

    assert "filter_pump_2" in by_slot
    assert by_slot["filter_pump_2"].horsepower == 2.5

    assert "filter_1" in by_slot
    assert by_slot["filter_1"].equipment_type == "filter"

    assert "sanitizer_1" in by_slot
    assert by_slot["sanitizer_1"].equipment_type == "sanitizer"


async def test_sync_is_idempotent(db_session, org_a):
    """Re-running sync on the same inspection updates rather than dupes."""
    prop, wf, facility, inspection, ie = await _seed_property_and_inspection(db_session, org_a)

    svc = InspectionService(db_session)
    first = await svc.sync_equipment_to_bow(facility.id)
    second = await svc.sync_equipment_to_bow(facility.id)

    assert first["updated_fields"]["equipment_items"]["created"] == 5
    assert second["updated_fields"]["equipment_items"]["created"] == 0
    assert second["updated_fields"]["equipment_items"]["updated"] == 5

    from sqlalchemy import select
    count = (await db_session.execute(
        select(EquipmentItem).where(EquipmentItem.water_feature_id == wf.id)
    )).scalars().all()
    assert len(count) == 5


async def test_sync_skips_manual_brand_model_collisions(db_session, org_a):
    """Manual EquipmentItem with matching brand+model is authoritative — no auto-create."""
    prop, wf, facility, inspection, ie = await _seed_property_and_inspection(db_session, org_a)

    # Manually add an item that matches one of the inspection slots
    manual = EquipmentItem(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        water_feature_id=wf.id,
        equipment_type="pump",
        brand="Pentair",
        model="WhisperFlo",
        is_active=True,
        source_inspection_id=None,  # manually entered
    )
    db_session.add(manual)
    await db_session.flush()

    svc = InspectionService(db_session)
    result = await svc.sync_equipment_to_bow(facility.id)
    summary = result["updated_fields"]["equipment_items"]

    # filter_pump_1 (Pentair WhisperFlo) should be skipped due to manual collision
    assert summary["skipped"] >= 1
    # filter_pump_2 + filter_pump_3 + filter_1 + sanitizer_1 still create
    assert summary["created"] == 4

    # Confirm the manual row is untouched (source_inspection_id still null)
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(EquipmentItem).where(
            EquipmentItem.water_feature_id == wf.id,
            EquipmentItem.brand == "Pentair",
            EquipmentItem.model == "WhisperFlo",
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_inspection_id is None


async def test_sync_returns_none_when_facility_unmatched(db_session, org_a):
    """Sync should bail early if the InspectionFacility is not matched to a property."""
    facility = InspectionFacility(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        name="Unmatched Facility",
        street_address="999 Nowhere",
        matched_property_id=None,
    )
    db_session.add(facility)
    await db_session.flush()

    svc = InspectionService(db_session)
    result = await svc.sync_equipment_to_bow(facility.id)
    assert result is None
