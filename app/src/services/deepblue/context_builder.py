"""Build rich context from entity IDs for DeepBlue system prompt."""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import json

from src.models.customer import Customer
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.models.equipment_item import EquipmentItem
from src.models.chemical_reading import ChemicalReading
from src.models.visit import Visit
from src.models.organization import Organization

logger = logging.getLogger(__name__)


@dataclass
class DeepBlueContext:
    customer_id: str | None = None
    property_id: str | None = None
    bow_id: str | None = None
    visit_id: str | None = None

    # Resolved data (populated by build())
    customer_name: str | None = None
    customer_type: str | None = None
    company_name: str | None = None
    properties: list[dict] = field(default_factory=list)
    equipment: list[dict] = field(default_factory=list)
    recent_readings: list[dict] = field(default_factory=list)
    recent_visits: list[dict] = field(default_factory=list)
    context_summary: str = ""


async def build_context(db: AsyncSession, org_id: str, ctx: DeepBlueContext) -> DeepBlueContext:
    """Resolve entity IDs into rich context data."""
    lines = []

    # Organization profile — always included so DeepBlue knows its own company
    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    if org:
        lines.append(f"=== YOUR ORGANIZATION ===")
        lines.append(f"Company: {org.name}")
        if org.phone:
            lines.append(f"Phone: {org.phone}")
        if org.email:
            lines.append(f"Email: {org.email}")
        if org.tagline:
            lines.append(f"Tagline: {org.tagline}")
        if org.agent_service_area:
            lines.append(f"Service area: {org.agent_service_area}")

        # Resolve structured addresses
        if org.addresses:
            try:
                raw = json.loads(org.addresses)
                for key in ("mailing", "physical", "billing"):
                    val = raw.get(key)
                    if not val:
                        continue
                    if isinstance(val, dict) and "same_as" in val:
                        source = raw.get(val["same_as"], {})
                        if isinstance(source, dict) and "same_as" not in source:
                            val = source
                            lines.append(f"{key.capitalize()} address: (same as {raw['mailing'].get('street') and 'mailing'})")
                            continue
                    street = val.get("street", "")
                    city = val.get("city", "")
                    state = val.get("state", "")
                    zip_code = val.get("zip", "")
                    if street or city:
                        lines.append(f"{key.capitalize()} address: {street}, {city} {state} {zip_code}".strip(", "))
            except (json.JSONDecodeError, TypeError):
                pass
        elif org.address:
            lines.append(f"Address: {org.address}, {org.city or ''} {org.state or ''} {org.zip_code or ''}".strip())
        lines.append("")  # blank line separator

    # Customer
    if ctx.customer_id:
        cust = (await db.execute(
            select(Customer).where(Customer.id == ctx.customer_id, Customer.organization_id == org_id)
        )).scalar_one_or_none()
        if cust:
            ctx.customer_name = cust.display_name
            ctx.customer_type = cust.customer_type
            ctx.company_name = cust.company_name
            lines.append(f"Customer: {cust.display_name} ({cust.customer_type or 'unknown'})")
            if cust.company_name:
                lines.append(f"Company: {cust.company_name}")
            if cust.monthly_rate:
                lines.append(f"Monthly rate: ${cust.monthly_rate:.2f}")
            if cust.preferred_day:
                lines.append(f"Service days: {cust.preferred_day}")

    # Properties
    prop_query = select(Property).where(Property.organization_id == org_id, Property.is_active == True)
    if ctx.property_id:
        prop_query = prop_query.where(Property.id == ctx.property_id)
    elif ctx.customer_id:
        prop_query = prop_query.where(Property.customer_id == ctx.customer_id)
    else:
        prop_query = None

    if prop_query is not None:
        props = (await db.execute(prop_query)).scalars().all()
        for p in props:
            prop_info = {"id": p.id, "address": p.full_address, "name": p.name}
            lines.append(f"\nProperty: {p.name or p.full_address}")
            if p.gate_code:
                lines.append(f"  Gate code: {p.gate_code}")

            # Bodies of water
            wfs = (await db.execute(
                select(WaterFeature).where(WaterFeature.property_id == p.id, WaterFeature.is_active == True)
            )).scalars().all()
            for wf in wfs:
                wf_line = f"  {wf.name or wf.water_type}"
                if wf.pool_gallons:
                    wf_line += f" — {wf.pool_gallons:,} gallons"
                if wf.sanitizer_type:
                    wf_line += f", {wf.sanitizer_type}"
                lines.append(wf_line)

                # Equipment on this water feature
                equip = (await db.execute(
                    select(EquipmentItem)
                    .options(selectinload(EquipmentItem.catalog_equipment))
                    .where(EquipmentItem.water_feature_id == wf.id, EquipmentItem.is_active == True)
                )).scalars().all()
                for ei in equip:
                    name = (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                            ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip())
                    eq_info = {
                        "id": ei.id,
                        "type": ei.equipment_type,
                        "name": name,
                        "brand": ei.brand,
                        "model": ei.model,
                        "catalog_id": ei.catalog_equipment_id,
                    }
                    ctx.equipment.append(eq_info)
                    lines.append(f"    Equipment: {ei.equipment_type} — {name}")

            ctx.properties.append(prop_info)

    # Recent chemical readings (last 5)
    reading_query = select(ChemicalReading).order_by(ChemicalReading.created_at.desc()).limit(5)
    if ctx.bow_id:
        reading_query = reading_query.where(ChemicalReading.water_feature_id == ctx.bow_id)
    elif ctx.property_id:
        reading_query = reading_query.where(ChemicalReading.property_id == ctx.property_id)
    elif ctx.customer_id:
        # Get property IDs for this customer
        prop_ids = [p["id"] for p in ctx.properties]
        if prop_ids:
            reading_query = reading_query.where(ChemicalReading.property_id.in_(prop_ids))
        else:
            reading_query = None

    if reading_query is not None:
        readings = (await db.execute(reading_query)).scalars().all()
        if readings:
            lines.append("\nRecent chemical readings:")
            for r in readings:
                parts = []
                if r.ph is not None:
                    parts.append(f"pH {r.ph}")
                if r.free_chlorine is not None:
                    parts.append(f"FC {r.free_chlorine}")
                if r.alkalinity is not None:
                    parts.append(f"TA {r.alkalinity}")
                if r.calcium_hardness is not None:
                    parts.append(f"CH {r.calcium_hardness}")
                if r.cyanuric_acid is not None:
                    parts.append(f"CYA {r.cyanuric_acid}")
                date_str = r.created_at.strftime("%m/%d") if r.created_at else "?"
                ctx.recent_readings.append({
                    "date": date_str, "ph": r.ph, "free_chlorine": r.free_chlorine,
                    "alkalinity": r.alkalinity, "calcium_hardness": r.calcium_hardness,
                    "cyanuric_acid": r.cyanuric_acid, "phosphates": r.phosphates,
                })
                lines.append(f"  {date_str}: {', '.join(parts)}")

    # Recent visits (last 5)
    if ctx.property_id:
        visits = (await db.execute(
            select(Visit).where(Visit.property_id == ctx.property_id)
            .order_by(Visit.scheduled_date.desc()).limit(5)
        )).scalars().all()
        if visits:
            lines.append("\nRecent visits:")
            for v in visits:
                date_str = v.scheduled_date.strftime("%m/%d") if v.scheduled_date else "?"
                tech = v.tech_id or "unknown"
                notes = f" — {v.notes[:60]}" if v.notes else ""
                lines.append(f"  {date_str} by {tech}{notes}")
                ctx.recent_visits.append({"date": date_str, "tech": tech, "notes": v.notes})

    ctx.context_summary = "\n".join(lines) if lines else "No specific context — user is on the general dashboard."
    return ctx
