"""EMD Service — orchestrates scraping, PDF extraction, facility matching, and lead generation."""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import selectinload

from src.models.emd_facility import EMDFacility
from src.models.emd_inspection import EMDInspection
from src.models.emd_violation import EMDViolation
from src.models.emd_equipment import EMDEquipment
from src.models.property import Property
from src.models.customer import Customer

logger = logging.getLogger(__name__)

UPLOADS_EMD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "emd")


class EMDService:
    """Orchestrates EMD scraping, data processing, and analysis."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Scraping ---

    async def scrape_date_range(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        rate_limit_seconds: int = 5,
    ) -> dict:
        """Scrape inspections for a date range and save to database.

        Returns summary dict with counts.
        """
        from src.services.emd.scraper import EMDScraper

        scraper = EMDScraper(rate_limit_seconds=rate_limit_seconds)
        try:
            facilities_data = await scraper.scrape_date_range(start_date, end_date)

            new_facilities = 0
            new_inspections = 0
            skipped = 0

            for fdata in facilities_data:
                result = await self.process_facility(fdata)
                if result == "new_inspection":
                    new_inspections += 1
                elif result == "new_facility":
                    new_facilities += 1
                    new_inspections += 1
                else:
                    skipped += 1

            await self.db.flush()

            return {
                "scraped": len(facilities_data),
                "new_facilities": new_facilities,
                "new_inspections": new_inspections,
                "skipped": skipped,
            }
        finally:
            await scraper.close()

    async def process_facility(self, facility_data: dict, pdf_path: Optional[str] = None) -> str:
        """Process a single scraped facility. Returns 'new_facility', 'new_inspection', or 'skipped'."""
        name = facility_data.get("name", "").strip()
        if not name:
            return "skipped"

        inspection_id = facility_data.get("inspection_id")

        # Check if inspection already exists
        if inspection_id:
            existing = await self.db.execute(
                select(EMDInspection).where(EMDInspection.inspection_id == inspection_id)
            )
            if existing.scalar_one_or_none():
                return "skipped"

        # Find or create facility
        facility, was_created = await self._find_or_create_facility(name, facility_data)
        result_type = "new_facility" if was_created else "new_inspection"

        # Create inspection record
        inspection_date = None
        if facility_data.get("inspection_date"):
            try:
                inspection_date = datetime.strptime(facility_data["inspection_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        inspection = EMDInspection(
            id=str(uuid.uuid4()),
            facility_id=facility.id,
            inspection_id=inspection_id,
            inspection_date=inspection_date,
            pdf_path=pdf_path,
        )
        self.db.add(inspection)

        # If PDF provided, extract data
        if pdf_path and os.path.exists(pdf_path):
            await self._process_pdf(inspection, facility, pdf_path)

        return result_type

    async def _find_or_create_facility(self, name: str, data: dict) -> tuple[EMDFacility, bool]:
        """Find existing facility by name or facility_id, or create new one.
        Returns (facility, was_created)."""
        # Try matching by EMD facility_id first
        emd_fid = data.get("facility_id")
        if emd_fid:
            result = await self.db.execute(
                select(EMDFacility).where(EMDFacility.facility_id == emd_fid)
            )
            facility = result.scalar_one_or_none()
            if facility:
                return facility, False

        # Try matching by name (case-insensitive)
        result = await self.db.execute(
            select(EMDFacility).where(func.lower(EMDFacility.name) == name.lower())
        )
        facility = result.scalar_one_or_none()
        if facility:
            return facility, False

        # Parse address
        address = data.get("address", "")
        street, city, state, zip_code = self._parse_address(address)

        facility = EMDFacility(
            id=str(uuid.uuid4()),
            name=name,
            street_address=street,
            city=city,
            state=state or "CA",
            zip_code=zip_code,
            facility_id=emd_fid,
            permit_holder=data.get("permit_holder"),
            phone=data.get("phone"),
            facility_type=data.get("facility_type"),
        )
        self.db.add(facility)
        await self.db.flush()
        return facility, True

    async def _process_pdf(self, inspection: EMDInspection, facility: EMDFacility, pdf_path: str):
        """Extract data from PDF and update inspection + create violations/equipment."""
        from src.services.emd.pdf_extractor import EMDPDFExtractor

        extractor = EMDPDFExtractor()
        data = extractor.extract_all(pdf_path)

        # Update inspection from PDF data
        if data.get("inspection_date"):
            try:
                inspection.inspection_date = datetime.strptime(data["inspection_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        violations = data.get("violations", [])
        inspection.total_violations = len(violations)
        inspection.major_violations = sum(1 for v in violations if v.get("is_major_violation"))
        inspection.report_notes = data.get("notes")

        # Save violations
        for v in violations:
            violation = EMDViolation(
                id=str(uuid.uuid4()),
                inspection_id=inspection.id,
                facility_id=facility.id,
                violation_code=v.get("violation_code"),
                violation_title=v.get("violation_title"),
                observations=v.get("observations"),
                is_major_violation=v.get("is_major_violation", False),
            )
            self.db.add(violation)

        # Save equipment
        equip_data = data.get("equipment", {})
        if equip_data:
            equipment = EMDEquipment(
                id=str(uuid.uuid4()),
                inspection_id=inspection.id,
                facility_id=facility.id,
                pool_capacity_gallons=equip_data.get("pool_capacity_gallons"),
                flow_rate_gpm=equip_data.get("flow_rate_gpm"),
                filter_pump_1_make=equip_data.get("filter_pump_1_make"),
                filter_pump_1_model=equip_data.get("filter_pump_1_model"),
                filter_pump_1_hp=equip_data.get("filter_pump_1_hp"),
                filter_1_type=equip_data.get("filter_1_type"),
                filter_1_make=equip_data.get("filter_1_make"),
                filter_1_model=equip_data.get("filter_1_model"),
                sanitizer_1_type=equip_data.get("sanitizer_1_type"),
                sanitizer_1_details=equip_data.get("sanitizer_1_details"),
                main_drain_type=equip_data.get("main_drain_type"),
                main_drain_model=equip_data.get("main_drain_model"),
                main_drain_install_date=equip_data.get("main_drain_install_date"),
                equalizer_model=equip_data.get("equalizer_model"),
                equalizer_install_date=equip_data.get("equalizer_install_date"),
            )
            self.db.add(equipment)

            # Update inspection-level pool data
            if equip_data.get("pool_capacity_gallons"):
                inspection.pool_capacity_gallons = equip_data["pool_capacity_gallons"]
            if equip_data.get("flow_rate_gpm"):
                inspection.flow_rate_gpm = equip_data["flow_rate_gpm"]

    # --- Facility matching ---

    async def match_facility_to_property(
        self, facility_id: str, property_id: str, organization_id: str
    ) -> EMDFacility:
        """Manually match an EMD facility to a QuantumPools property."""
        result = await self.db.execute(
            select(EMDFacility).where(EMDFacility.id == facility_id)
        )
        facility = result.scalar_one_or_none()
        if not facility:
            raise ValueError(f"EMD facility {facility_id} not found")

        # Verify property exists
        result = await self.db.execute(
            select(Property).where(
                Property.id == property_id,
                Property.organization_id == organization_id,
            )
        )
        prop = result.scalar_one_or_none()
        if not prop:
            raise ValueError(f"Property {property_id} not found")

        facility.matched_property_id = property_id
        facility.matched_at = datetime.now(timezone.utc)
        facility.organization_id = organization_id
        await self.db.flush()
        return facility

    async def auto_match_facilities(self, organization_id: str) -> dict:
        """Try to auto-match unmatched EMD facilities to properties by address similarity."""
        # Get unmatched facilities
        result = await self.db.execute(
            select(EMDFacility).where(EMDFacility.matched_property_id.is_(None))
        )
        unmatched = result.scalars().all()

        # Get all org properties
        result = await self.db.execute(
            select(Property).where(
                Property.organization_id == organization_id,
                Property.is_active == True,
            )
        )
        properties = result.scalars().all()

        matched = 0
        for facility in unmatched:
            if not facility.street_address:
                continue

            fac_addr = self._normalize_address(facility.street_address)
            for prop in properties:
                prop_addr = self._normalize_address(prop.address)
                if fac_addr and prop_addr and fac_addr == prop_addr:
                    facility.matched_property_id = prop.id
                    facility.matched_at = datetime.now(timezone.utc)
                    facility.organization_id = organization_id
                    matched += 1
                    break

        await self.db.flush()
        return {"total_unmatched": len(unmatched), "matched": matched}

    # --- Queries ---

    async def list_facilities(
        self,
        search: Optional[str] = None,
        matched_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List EMD facilities with summary stats including closure info."""
        # Count subqueries
        inspection_count = (
            select(func.count(EMDInspection.id))
            .where(EMDInspection.facility_id == EMDFacility.id)
            .correlate(EMDFacility)
            .scalar_subquery()
        )
        violation_count = (
            select(func.count(EMDViolation.id))
            .where(EMDViolation.facility_id == EMDFacility.id)
            .correlate(EMDFacility)
            .scalar_subquery()
        )
        last_inspection = (
            select(func.max(EMDInspection.inspection_date))
            .where(EMDInspection.facility_id == EMDFacility.id)
            .correlate(EMDFacility)
            .scalar_subquery()
        )

        query = select(
            EMDFacility,
            inspection_count.label("total_inspections"),
            violation_count.label("total_violations"),
            last_inspection.label("last_inspection_date"),
        )

        if search:
            query = query.where(
                EMDFacility.name.ilike(f"%{search}%")
                | EMDFacility.street_address.ilike(f"%{search}%")
                | EMDFacility.facility_id.ilike(f"%{search}%")
            )

        if matched_only:
            query = query.where(EMDFacility.matched_property_id.isnot(None))

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Fetch page
        query = query.order_by(desc(last_inspection)).limit(limit).offset(offset)
        result = await self.db.execute(query)
        rows = result.all()

        # Collect facility IDs for batch closure lookup
        facility_ids = [row[0].id for row in rows]

        # Batch lookup: for each facility, get the most recent inspection's closure_required
        closure_map: dict[str, bool] = {}
        closure_reasons_map: dict[str, list[str]] = {}
        if facility_ids:
            # Subquery: latest inspection date per facility
            latest_insp_sq = (
                select(
                    EMDInspection.facility_id,
                    func.max(EMDInspection.inspection_date).label("max_date"),
                )
                .where(EMDInspection.facility_id.in_(facility_ids))
                .group_by(EMDInspection.facility_id)
                .subquery()
            )
            # Join back to get the actual inspection rows
            latest_inspections_result = await self.db.execute(
                select(EMDInspection)
                .join(
                    latest_insp_sq,
                    and_(
                        EMDInspection.facility_id == latest_insp_sq.c.facility_id,
                        EMDInspection.inspection_date == latest_insp_sq.c.max_date,
                    ),
                )
            )
            latest_inspections = latest_inspections_result.scalars().all()

            closed_inspection_ids = []
            for insp in latest_inspections:
                if insp.closure_required:
                    closure_map[insp.facility_id] = True
                    closed_inspection_ids.append(insp.id)

            # For closed inspections, fetch closure reasons from violations
            # Standard violation code → short label mapping
            VIOLATION_LABELS = {
                "1a": "Gate Self-Close/Latch", "1b": "Gate Hardware", "1c": "Emergency Exit Gate",
                "2a": "Pool Enclosure", "2b": "Non-Climbable Enclosure",
                "3": "Safety Signs", "4": "Safety Equipment",
                "10a": "Low Chlorine", "10b": "High Chlorine",
                "12a": "Low pH", "12b": "High pH", "13": "High CYA",
                "16": "Water Clarity", "24": "VGB Suction Covers",
                "37": "Electrical Hazards", "43": "EMD Approval Required", "46": "Other",
            }

            if closed_inspection_ids:
                violation_result = await self.db.execute(
                    select(EMDViolation.facility_id, EMDViolation.violation_code, EMDViolation.violation_title)
                    .where(
                        EMDViolation.inspection_id.in_(closed_inspection_ids),
                        EMDViolation.observations.ilike("MAJOR VIOLATION - CLOSURE:%"),
                    )
                )
                for vrow in violation_result.all():
                    code = (vrow.violation_code or "").strip().lower()
                    label = VIOLATION_LABELS.get(code, vrow.violation_title or "Violation")
                    if label and label not in closure_reasons_map.get(vrow.facility_id, []):
                        closure_reasons_map.setdefault(vrow.facility_id, []).append(label)

        facilities = []
        for row in rows:
            fac = row[0]
            facilities.append({
                "id": fac.id,
                "name": fac.name,
                "street_address": fac.street_address,
                "city": fac.city,
                "facility_id": fac.facility_id,
                "facility_type": fac.facility_type,
                "matched_property_id": fac.matched_property_id,
                "total_inspections": row.total_inspections or 0,
                "total_violations": row.total_violations or 0,
                "last_inspection_date": row.last_inspection_date,
                "is_closed": closure_map.get(fac.id, False),
                "closure_reasons": closure_reasons_map.get(fac.id, []),
            })

        return facilities, total

    async def get_facility_detail(self, facility_id: str) -> Optional[dict]:
        """Get facility with full inspection history."""
        result = await self.db.execute(
            select(EMDFacility).where(EMDFacility.id == facility_id)
        )
        facility = result.scalar_one_or_none()
        if not facility:
            return None

        # Get inspections with violations
        result = await self.db.execute(
            select(EMDInspection)
            .where(EMDInspection.facility_id == facility_id)
            .options(selectinload(EMDInspection.violations), selectinload(EMDInspection.equipment))
            .order_by(desc(EMDInspection.inspection_date))
        )
        inspections = result.scalars().all()

        # Get matched property info
        matched_property_address = None
        matched_customer_name = None
        if facility.matched_property_id:
            result = await self.db.execute(
                select(Property, Customer)
                .join(Customer, Property.customer_id == Customer.id)
                .where(Property.id == facility.matched_property_id)
            )
            row = result.first()
            if row:
                matched_property_address = row[0].full_address
                matched_customer_name = row[1].display_name_col

        total_violations = sum(i.total_violations for i in inspections)
        last_date = inspections[0].inspection_date if inspections else None

        return {
            "facility": facility,
            "inspections": inspections,
            "total_inspections": len(inspections),
            "total_violations": total_violations,
            "last_inspection_date": last_date,
            "matched_property_address": matched_property_address,
            "matched_customer_name": matched_customer_name,
        }

    async def get_facility_inspections(self, facility_id: str) -> list[EMDInspection]:
        """Get all inspections for a facility."""
        result = await self.db.execute(
            select(EMDInspection)
            .where(EMDInspection.facility_id == facility_id)
            .options(selectinload(EMDInspection.violations))
            .order_by(desc(EMDInspection.inspection_date))
        )
        return result.scalars().all()

    async def get_facility_equipment(self, facility_id: str) -> Optional[EMDEquipment]:
        """Get the latest equipment data for a facility."""
        result = await self.db.execute(
            select(EMDEquipment)
            .join(EMDInspection, EMDEquipment.inspection_id == EMDInspection.id)
            .where(EMDEquipment.facility_id == facility_id)
            .order_by(desc(EMDInspection.inspection_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_property_inspections(self, property_id: str) -> list[EMDInspection]:
        """Get inspections for a matched property."""
        result = await self.db.execute(
            select(EMDInspection)
            .join(EMDFacility, EMDInspection.facility_id == EMDFacility.id)
            .where(EMDFacility.matched_property_id == property_id)
            .options(selectinload(EMDInspection.violations))
            .order_by(desc(EMDInspection.inspection_date))
        )
        return result.scalars().all()

    # --- Lead generation ---

    async def get_high_violation_facilities(
        self,
        min_violations: int = 3,
        days: int = 365,
    ) -> list[dict]:
        """Find facilities with recurring violations — potential leads for pool service."""
        cutoff = date.today() - timedelta(days=days)

        # Subquery for recent violation counts
        recent_violations = (
            select(
                EMDViolation.facility_id,
                func.count(EMDViolation.id).label("violation_count"),
            )
            .join(EMDInspection, EMDViolation.inspection_id == EMDInspection.id)
            .where(EMDInspection.inspection_date >= cutoff)
            .group_by(EMDViolation.facility_id)
            .having(func.count(EMDViolation.id) >= min_violations)
            .subquery()
        )

        result = await self.db.execute(
            select(
                EMDFacility.id,
                EMDFacility.name,
                EMDFacility.street_address,
                EMDFacility.city,
                EMDFacility.matched_property_id,
                recent_violations.c.violation_count,
            )
            .join(recent_violations, EMDFacility.id == recent_violations.c.facility_id)
            .order_by(desc(recent_violations.c.violation_count))
        )
        rows = result.all()

        leads = []
        for row in rows:
            # Get inspection count and last date
            insp_result = await self.db.execute(
                select(
                    func.count(EMDInspection.id),
                    func.max(EMDInspection.inspection_date),
                )
                .where(
                    EMDInspection.facility_id == row.id,
                    EMDInspection.inspection_date >= cutoff,
                )
            )
            insp_row = insp_result.first()

            # Count major violations
            major_result = await self.db.execute(
                select(func.count(EMDViolation.id))
                .join(EMDInspection, EMDViolation.inspection_id == EMDInspection.id)
                .where(
                    EMDViolation.facility_id == row.id,
                    EMDViolation.is_major_violation == True,
                    EMDInspection.inspection_date >= cutoff,
                )
            )
            major_count = major_result.scalar() or 0

            leads.append({
                "facility_id": row.id,
                "facility_name": row.name,
                "street_address": row.street_address,
                "city": row.city,
                "total_inspections": insp_row[0] if insp_row else 0,
                "total_violations": row.violation_count,
                "major_violations": major_count,
                "last_inspection_date": insp_row[1] if insp_row else None,
                "is_matched": row.matched_property_id is not None,
                "violation_trend": "stable",
            })

        return leads

    # --- Sync equipment to BOW ---

    async def sync_equipment_to_bow(self, facility_id: str) -> Optional[dict]:
        """Copy latest EMD equipment data to the matched property's primary BOW."""
        from src.models.body_of_water import BodyOfWater

        # Get facility with match
        result = await self.db.execute(
            select(EMDFacility).where(EMDFacility.id == facility_id)
        )
        facility = result.scalar_one_or_none()
        if not facility or not facility.matched_property_id:
            return None

        # Get latest equipment
        equipment = await self.get_facility_equipment(facility_id)
        if not equipment:
            return None

        # Get primary BOW for the property
        result = await self.db.execute(
            select(BodyOfWater).where(
                BodyOfWater.property_id == facility.matched_property_id,
                BodyOfWater.is_primary == True,
            )
        )
        bow = result.scalar_one_or_none()
        if not bow:
            return None

        # Sync pool specs
        updated = {}
        if equipment.pool_capacity_gallons and not bow.pool_gallons:
            bow.pool_gallons = equipment.pool_capacity_gallons
            updated["pool_gallons"] = equipment.pool_capacity_gallons

        await self.db.flush()
        return {"bow_id": bow.id, "updated_fields": updated}

    # --- Helpers ---

    @staticmethod
    def _parse_address(address: str) -> tuple[str, str, str, str]:
        """Parse an address string into (street, city, state, zip)."""
        if not address or address == "Unknown":
            return ("", "", "CA", "")

        parts = [p.strip() for p in address.split(",")]
        street = parts[0] if len(parts) > 0 else ""
        city = parts[1] if len(parts) > 1 else ""
        state_zip = parts[2] if len(parts) > 2 else ""

        state = "CA"
        zip_code = ""
        if state_zip:
            sz_parts = state_zip.strip().split()
            if len(sz_parts) >= 2:
                state = sz_parts[0]
                zip_code = sz_parts[1]
            elif len(sz_parts) == 1:
                if sz_parts[0].isdigit():
                    zip_code = sz_parts[0]
                else:
                    state = sz_parts[0]

        return (street, city, state, zip_code)

    @staticmethod
    def _normalize_address(address: str) -> str:
        """Normalize address for comparison."""
        import re
        if not address:
            return ""
        addr = address.lower().strip()
        # Remove unit/suite/apt numbers
        addr = re.sub(r"\s*#\s*\d+", "", addr)
        addr = re.sub(r"\s*(suite|ste|apt|unit)\s*\w*", "", addr, flags=re.I)
        # Standardize abbreviations
        addr = addr.replace(" street", " st").replace(" avenue", " ave")
        addr = addr.replace(" boulevard", " blvd").replace(" drive", " dr")
        addr = addr.replace(" road", " rd").replace(" lane", " ln")
        addr = addr.replace(" court", " ct").replace(" place", " pl")
        # Remove extra spaces
        addr = re.sub(r"\s+", " ", addr).strip()
        return addr
