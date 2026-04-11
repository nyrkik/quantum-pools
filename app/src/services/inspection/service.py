"""EMD Service — orchestrates scraping, PDF extraction, facility matching, and lead generation."""

import os
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import selectinload

from src.models.inspection_facility import InspectionFacility
from src.models.inspection import Inspection
from src.models.inspection_violation import InspectionViolation
from src.models.inspection_equipment import InspectionEquipment
from src.models.property import Property
from src.models.customer import Customer

logger = logging.getLogger(__name__)

VIOLATION_LABELS = {
    "1a": "Gate Self-Close/Latch", "1b": "Gate Hardware", "1c": "Emergency Exit Gate",
    "2a": "Pool Enclosure", "2b": "Non-Climbable Enclosure",
    "3": "Safety Signs", "4": "Safety Equipment",
    "10a": "Low Chlorine", "10b": "High Chlorine",
    "12a": "Low pH", "12b": "High pH", "13": "High CYA",
    "16": "Water Clarity", "24": "VGB Suction Covers",
    "37": "Electrical Hazards", "43": "EMD Approval Required", "46": "Other",
}

UPLOADS_EMD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "emd")


class InspectionService:
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
        from src.services.inspection.scraper import InspectionScraper

        scraper = InspectionScraper(rate_limit_seconds=rate_limit_seconds)
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

        inspection_id = facility_data.get("inspection_id")

        # Check if inspection already exists
        if inspection_id:
            existing = await self.db.execute(
                select(Inspection).where(Inspection.inspection_id == inspection_id)
            )
            if existing.scalar_one_or_none():
                return "skipped"

        # Pre-extract PDF data BEFORE dedup so we can use the canonical
        # Establishment ID (FA####) and the structured address fields, instead
        # of relying on the scraper's brittle name+address. Cache the parsed
        # data so _process_pdf doesn't have to parse the same PDF twice.
        pdf_data: Optional[dict] = None
        if pdf_path and os.path.exists(pdf_path):
            from src.services.inspection.pdf_extractor import EMDPDFExtractor
            try:
                pdf_data = EMDPDFExtractor().extract_all(pdf_path)
            except Exception as e:
                logger.warning(f"PDF extraction failed for {pdf_path}: {e}")
                pdf_data = None

            if pdf_data:
                # Merge PDF fields into facility_data only where missing.
                # PDF is the canonical source for facility_id and address fields.
                if not facility_data.get("facility_id") and pdf_data.get("facility_id"):
                    facility_data["facility_id"] = pdf_data["facility_id"]
                if not facility_data.get("permit_holder") and pdf_data.get("permit_holder"):
                    facility_data["permit_holder"] = pdf_data["permit_holder"]
                if not facility_data.get("phone") and pdf_data.get("phone_number"):
                    facility_data["phone"] = pdf_data["phone_number"]
                if pdf_data.get("facility_address"):
                    facility_data.setdefault("street_address", pdf_data["facility_address"])
                if pdf_data.get("facility_city"):
                    facility_data.setdefault("city", pdf_data["facility_city"])
                if pdf_data.get("facility_zip"):
                    facility_data.setdefault("zip_code", pdf_data["facility_zip"])
                # The program_identifier is the per-inspection discriminator
                # used to route a multi-building / multi-BoW establishment to
                # the right facility row. Always pull it from the PDF if
                # present — this is what `_find_or_create_facility` keys on.
                if pdf_data.get("program_identifier"):
                    facility_data["program_identifier"] = pdf_data["program_identifier"]
                # Use PDF facility_name as a fallback if scraper name is empty
                if not name and pdf_data.get("facility_name"):
                    name = pdf_data["facility_name"]

        if not name:
            return "skipped"

        # Find or create facility (now with PDF-enriched data)
        facility, was_created = await self._find_or_create_facility(name, facility_data)

        # If facility was found by name match but lacks the canonical FA####,
        # backfill it from the PDF — but only if no other facility already
        # owns that FA#### (the unique index would otherwise reject).
        if not facility.facility_id and facility_data.get("facility_id"):
            new_fid = facility_data["facility_id"]
            check = await self.db.execute(
                select(InspectionFacility.id).where(
                    InspectionFacility.facility_id == new_fid,
                    InspectionFacility.id != facility.id,
                )
            )
            if not check.first():
                facility.facility_id = new_fid

        result_type = "new_facility" if was_created else "new_inspection"

        # Create inspection record
        inspection_date = None
        if facility_data.get("inspection_date"):
            try:
                inspection_date = datetime.strptime(facility_data["inspection_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        inspection = Inspection(
            id=str(uuid.uuid4()),
            facility_id=facility.id,
            inspection_id=inspection_id,
            inspection_date=inspection_date,
            program_identifier="POOL",
            pdf_path=pdf_path,
            permit_url=facility_data.get("url"),
        )
        self.db.add(inspection)

        # If PDF provided, populate inspection fields and create violations/equipment.
        # Pass the already-extracted data so we don't re-parse the PDF.
        if pdf_path and os.path.exists(pdf_path):
            await self._process_pdf(inspection, facility, pdf_path, pdf_data=pdf_data)

        return result_type

    async def _find_or_create_facility(self, name: str, data: dict) -> tuple[InspectionFacility, bool]:
        """Find or create the inspection_facility row that owns this inspection.

        Dedup key: (facility_id, program_identifier). One EMD establishment
        (FA####) can have multiple facility rows distinguished by
        program_identifier (e.g. POOL vs SPA, or "POOL @ 4407 OAK HOLLOW DR"
        vs "POOL @ 4440 OAK HOLLOW DR" for one establishment with two
        physical buildings — Arbor Ridge case).

        Resolution order when an FA already has rows:
          1. Exact (FA, program_identifier) match → use it
          2. NULL-program row exists → AUTO-SPLIT: clone its address/metadata
             into a new row with the new program_identifier so subsequent
             inspections at this program land in the right place
          3. No NULL row either → create a new row alongside the existing
             ones, copying address/metadata from the first
        """
        emd_fid = data.get("facility_id")
        program_id = data.get("program_identifier")  # set by process_facility from PDF

        if emd_fid:
            result = await self.db.execute(
                select(InspectionFacility).where(InspectionFacility.facility_id == emd_fid)
            )
            candidates = result.scalars().all()

            if candidates:
                # 1. Exact match on (FA, program_identifier)
                if program_id is not None:
                    exact = next(
                        (f for f in candidates if f.program_identifier == program_id),
                        None,
                    )
                    if exact:
                        return exact, False

                    # 2. If the FA has only one row and it's a NULL-program
                    # generic row, UPDATE it in place rather than splitting.
                    # This avoids leaving orphaned NULL rows behind during
                    # realignment, while still allowing future splits when
                    # a third distinct program_id shows up.
                    if len(candidates) == 1 and candidates[0].program_identifier is None:
                        candidates[0].program_identifier = program_id
                        await self.db.flush()
                        return candidates[0], False

                    # 3. Auto-split off a NULL-program row (or any existing row)
                    generic = next(
                        (f for f in candidates if f.program_identifier is None),
                        None,
                    )
                    template = generic or candidates[0]
                    # If the program_identifier has an "@ <address>" suffix
                    # (the Arbor Ridge multi-building pattern), use that as
                    # the new row's street_address so auto_match can link it
                    # to the right customer property. Otherwise inherit.
                    program_addr = self._extract_program_address(program_id)
                    new_row = InspectionFacility(
                        id=str(uuid.uuid4()),
                        name=name or template.name,
                        facility_id=emd_fid,
                        program_identifier=program_id,
                        street_address=program_addr or data.get("street_address") or template.street_address,
                        city=data.get("city") or template.city,
                        state=template.state or "CA",
                        zip_code=data.get("zip_code") or template.zip_code,
                        permit_holder=data.get("permit_holder") or template.permit_holder,
                        phone=data.get("phone") or template.phone,
                        facility_type=data.get("facility_type") or template.facility_type,
                    )
                    self.db.add(new_row)
                    await self.db.flush()
                    logger.info(
                        f"Auto-split facility {emd_fid}: new row for program_identifier={program_id!r}"
                    )
                    return new_row, True
                else:
                    # No program_identifier — fall back to the existing
                    # generic catch-all (NULL) or any existing row
                    generic = next(
                        (f for f in candidates if f.program_identifier is None),
                        None,
                    )
                    return (generic or candidates[0]), False

        # Fallback: case-insensitive name match. ONLY runs when we have no
        # FA#### at all (e.g. PDF extraction failed). If FA was provided but
        # didn't match an existing row, fall straight through to creation
        # rather than risk colliding with a same-named facility at a different
        # FA (real-world: multiple "In-Shape Fitness" locations).
        if not emd_fid:
            result = await self.db.execute(
                select(InspectionFacility).where(func.lower(InspectionFacility.name) == name.lower())
            )
            # Use .first() not scalar_one_or_none() — same name can repeat
            # across facility rows now that we allow multi-row per FA.
            facility = result.scalars().first()
            if facility:
                return facility, False

        # Prefer structured address fields from PDF; fall back to parsing the
        # scraper's address string.
        street = data.get("street_address")
        city = data.get("city")
        zip_code = data.get("zip_code")
        state = None
        if not street or not city:
            ps, pc, pst, pz = self._parse_address(data.get("address", ""))
            street = street or ps
            city = city or pc
            state = pst
            zip_code = zip_code or pz

        facility = InspectionFacility(
            id=str(uuid.uuid4()),
            name=name,
            street_address=street or "",
            city=city or "",
            state=state or "CA",
            zip_code=zip_code or "",
            facility_id=emd_fid,
            program_identifier=program_id,
            permit_holder=data.get("permit_holder"),
            phone=data.get("phone"),
            facility_type=data.get("facility_type"),
        )
        self.db.add(facility)
        await self.db.flush()
        return facility, True

    async def _process_pdf(self, inspection: Inspection, facility: InspectionFacility, pdf_path: str, pdf_data: Optional[dict] = None):
        """Extract data from PDF and update inspection + create violations/equipment.

        If `pdf_data` is provided, uses it instead of re-parsing the PDF
        (process_facility extracts early so dedup can use the canonical FA####).
        """
        if pdf_data is None:
            from src.services.inspection.pdf_extractor import EMDPDFExtractor
            pdf_data = EMDPDFExtractor().extract_all(pdf_path)

        data = pdf_data

        # Update inspection from PDF data
        if data.get("inspection_date"):
            try:
                inspection.inspection_date = datetime.strptime(data["inspection_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Save program identifier and permit ID on the inspection
        inspection.program_identifier = data.get("program_identifier") or "POOL"
        if data.get("permit_id"):
            inspection.permit_id = data["permit_id"]

        violations = data.get("violations", [])
        inspection.total_violations = len(violations)
        inspection.major_violations = sum(1 for v in violations if v.get("is_major_violation"))
        inspection.report_notes = data.get("notes")

        # Save violations
        for v in violations:
            title = (v.get("violation_title") or "")[:500]
            code = (v.get("violation_code") or "")[:20]
            violation = InspectionViolation(
                id=str(uuid.uuid4()),
                inspection_id=inspection.id,
                facility_id=facility.id,
                violation_code=code,
                violation_title=title,
                observations=v.get("observations"),
                is_major_violation=v.get("is_major_violation", False),
            )
            self.db.add(violation)

        # Save equipment
        equip_data = data.get("equipment", {})
        if equip_data:
            equipment = InspectionEquipment(
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
    ) -> InspectionFacility:
        """Manually match an EMD facility to a QuantumPools property."""
        result = await self.db.execute(
            select(InspectionFacility).where(InspectionFacility.id == facility_id)
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
        """Auto-match unmatched EMD facilities to properties by normalized address.
        Also unmatches facilities linked to inactive customers.
        """
        import re

        # First: unmatch facilities linked to inactive customers
        unmatched_inactive = await self.db.execute(
            select(InspectionFacility)
            .join(Property, Property.id == InspectionFacility.matched_property_id)
            .join(Customer, Customer.id == Property.customer_id)
            .where(
                InspectionFacility.matched_property_id.isnot(None),
                Customer.is_active == False,
            )
        )
        removed = 0
        for fac in unmatched_inactive.scalars().all():
            fac.matched_property_id = None
            fac.matched_at = None
            fac.organization_id = None
            removed += 1
        if removed > 0:
            await self.db.flush()

        # Only consider facilities with a canonical Establishment ID (FA####).
        # Orphan stubs without an FA#### are remnants from the broken-scraper
        # era (see docs/inspection-scraper-recovery.md) and must never be
        # auto-matched — they can't be reliably distinguished from real ones.
        result = await self.db.execute(
            select(InspectionFacility).where(
                InspectionFacility.matched_property_id.is_(None),
                InspectionFacility.facility_id.isnot(None),
                InspectionFacility.facility_id != "",
            )
        )
        unmatched = result.scalars().all()

        result = await self.db.execute(
            select(Property)
            .join(Customer, Customer.id == Property.customer_id)
            .where(
                Property.organization_id == organization_id,
                Property.is_active == True,
                Customer.is_active == True,
            )
        )
        properties = result.scalars().all()

        # Build lookup by normalized address
        prop_by_addr = {}
        prop_by_street_key = {}
        for prop in properties:
            norm = self._normalize_address(prop.address)
            if norm:
                prop_by_addr[norm] = prop
            # Index by street number + street name for fuzzy fallback. Build
            # BOTH the single-word key (parts[1]) and the joined-words key
            # (parts[1] + parts[2] without the space) so EMD facilities like
            # "4440 OAK HOLLOW DR" can fuzzy-match against properties like
            # "4440 Oakhollow Dr". (Real-world: Arbor Ridge II.)
            parts = norm.split()
            if len(parts) >= 2 and parts[0].isdigit():
                # Single-word key
                key = f"{parts[0]} {parts[1]}"
                prop_by_street_key.setdefault(key, []).append(prop)
                # Joined-words key (only if there's a third part that isn't
                # a street type abbreviation like dr/st/ave)
                if len(parts) >= 3 and parts[2] not in {
                    "dr", "st", "ave", "blvd", "rd", "ln", "ct", "pl",
                    "pkwy", "cir", "ter", "wy", "way", "hwy",
                }:
                    joined_key = f"{parts[0]} {parts[1]}{parts[2]}"
                    prop_by_street_key.setdefault(joined_key, []).append(prop)

        matched = 0
        matches_detail = []
        for facility in unmatched:
            if not facility.street_address:
                continue

            fac_addr = self._normalize_address(facility.street_address)
            prop = prop_by_addr.get(fac_addr)

            # Fuzzy: match on street number + name if exact fails
            if not prop:
                parts = fac_addr.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    # Try the single-word key first, then the joined-words
                    # variant if the facility's address has multi-word street.
                    candidates = list(prop_by_street_key.get(f"{parts[0]} {parts[1]}", []))
                    if len(parts) >= 3 and parts[2] not in {
                        "dr", "st", "ave", "blvd", "rd", "ln", "ct", "pl",
                        "pkwy", "cir", "ter", "wy", "way", "hwy",
                    }:
                        joined_key = f"{parts[0]} {parts[1]}{parts[2]}"
                        candidates.extend(prop_by_street_key.get(joined_key, []))
                    # Filter by city if available
                    if facility.city and candidates:
                        city_match = [p for p in candidates if p.city and p.city.lower() == facility.city.lower()]
                        if city_match:
                            candidates = city_match
                    # Dedupe while preserving order
                    seen_ids = set()
                    unique_candidates = []
                    for c in candidates:
                        if c.id not in seen_ids:
                            seen_ids.add(c.id)
                            unique_candidates.append(c)
                    if len(unique_candidates) == 1:
                        prop = unique_candidates[0]

            if prop:
                facility.matched_property_id = prop.id
                facility.matched_at = datetime.now(timezone.utc)
                facility.organization_id = organization_id
                matched += 1
                matches_detail.append({"facility": facility.name, "property_address": prop.address})

        if matched > 0:
            await self.db.flush()
            logger.info(f"Auto-matched {matched} EMD facilities to properties")

        return {"total_unmatched": len(unmatched), "matched": matched, "removed": removed, "details": matches_detail}

    async def get_org_properties_emd_status(self, organization_id: str) -> list[dict]:
        """Get EMD match status for all commercial properties in the org.

        Auto-runs matching first, then returns status with reasons for unmatched.
        """
        # Auto-run matching before returning status
        try:
            await self.auto_match_facilities(organization_id)
            await self.db.commit()
        except Exception as e:
            logger.warning(f"Auto-match during status check failed: {e}")
            await self.db.rollback()

        result = await self.db.execute(
            select(Property, Customer)
            .join(Customer, Customer.id == Property.customer_id)
            .where(
                Property.organization_id == organization_id,
                Customer.customer_type == "commercial",
                Customer.is_active == True,
                Property.is_active == True,
            )
            .order_by(Customer.first_name)
        )
        rows = result.all()

        statuses = []
        for prop, cust in rows:
            # A property may legitimately be matched to >1 facility (separate
            # pool/spa permits). Aggregate stats across all matched facilities.
            fac_result = await self.db.execute(
                select(InspectionFacility).where(InspectionFacility.matched_property_id == prop.id)
            )
            facilities = fac_result.scalars().all()

            total_violations = 0
            last_date = None
            primary_facility = None

            if facilities:
                facility_ids = [f.id for f in facilities]
                stats = await self.db.execute(
                    select(
                        func.count(InspectionViolation.id),
                        func.max(Inspection.inspection_date),
                    )
                    .select_from(Inspection)
                    .outerjoin(InspectionViolation, InspectionViolation.inspection_id == Inspection.id)
                    .where(Inspection.facility_id.in_(facility_ids))
                )
                stat_row = stats.one()
                total_violations = stat_row[0] or 0
                last_date = stat_row[1]

                # Pick the facility with the most recent inspection as the
                # primary one for response shape (frontend expects scalar fields).
                primary_result = await self.db.execute(
                    select(InspectionFacility.id, func.max(Inspection.inspection_date).label("last"))
                    .join(Inspection, Inspection.facility_id == InspectionFacility.id)
                    .where(InspectionFacility.id.in_(facility_ids))
                    .group_by(InspectionFacility.id)
                    .order_by(desc("last"))
                    .limit(1)
                )
                primary_row = primary_result.first()
                if primary_row:
                    primary_facility = next((f for f in facilities if f.id == primary_row[0]), facilities[0])
                else:
                    primary_facility = facilities[0]

            # Determine reason for unmatched
            unmatched_reason = None
            if not facilities:
                county = getattr(prop, "county", None) or ""
                if county and county.lower() != "sacramento":
                    unmatched_reason = f"{county} County — not in Sacramento County database"
                else:
                    unmatched_reason = "No matching facility found in inspection database"

            statuses.append({
                "property_id": prop.id,
                "property_address": prop.full_address,
                "customer_name": cust.display_name_col,
                "customer_id": cust.id,
                "match_status": "matched" if facilities else "unmatched",
                "facility_id": primary_facility.id if primary_facility else None,
                "facility_name": primary_facility.name if primary_facility else None,
                "matched_facility_count": len(facilities),
                "last_inspection_date": last_date,
                "total_violations": total_violations,
                "unmatched_reason": unmatched_reason,
            })

        return statuses

    async def suggest_matches(self, property_id: str, organization_id: str) -> list[dict]:
        """Suggest top EMD facility matches for a property by address similarity."""
        prop_result = await self.db.execute(
            select(Property).where(Property.id == property_id, Property.organization_id == organization_id)
        )
        prop = prop_result.scalar_one_or_none()
        if not prop:
            return []

        prop_norm = self._normalize_address(prop.address)
        prop_parts = prop_norm.split()
        prop_number = prop_parts[0] if prop_parts and prop_parts[0].isdigit() else None
        prop_street = " ".join(prop_parts[1:]) if len(prop_parts) > 1 else ""
        prop_city = (prop.city or "").lower()

        # Get customer name for name matching
        cust_result = await self.db.execute(
            select(Customer).where(Customer.id == prop.customer_id)
        )
        customer = cust_result.scalar_one_or_none()
        cust_name_words = set((customer.display_name_col or "").lower().split()) if customer else set()
        # Remove generic words
        cust_name_words -= {"apartments", "apartment", "apts", "apt", "the", "at", "of", "and", "llc", "inc"}

        # Get all facilities (not already matched to another property)
        result = await self.db.execute(
            select(InspectionFacility).where(
                InspectionFacility.matched_property_id.is_(None) | (InspectionFacility.matched_property_id == property_id)
            )
        )
        facilities = result.scalars().all()

        scored = []
        for fac in facilities:
            fac_norm = self._normalize_address(fac.street_address) if fac.street_address else ""
            fac_parts = fac_norm.split()
            fac_number = fac_parts[0] if fac_parts and fac_parts[0].isdigit() else None
            fac_street = " ".join(fac_parts[1:]) if len(fac_parts) > 1 else ""
            fac_city = (fac.city or "").lower()

            score = 0

            # Address scoring
            if fac_norm and prop_norm == fac_norm:
                score = 100
            elif prop_street and fac_street:
                number_match = prop_number and fac_number and prop_number == fac_number
                # Close number (within 10) — catches 7000 vs 7002
                number_close = (prop_number and fac_number
                    and abs(int(prop_number) - int(fac_number)) <= 10)
                # Street name comparison
                street_exact = prop_street == fac_street
                prop_words = set(prop_street.split())
                fac_words = set(fac_street.split())
                street_overlap = len(prop_words & fac_words) / max(len(prop_words | fac_words), 1)

                if number_match and street_exact:
                    score = 90
                elif number_match and street_overlap >= 0.5:
                    score = 70
                elif number_close and street_exact:
                    score = 70
                elif number_close and street_overlap >= 0.5:
                    score = 55
                elif street_exact and prop_city == fac_city:
                    score = 40
                elif number_match and prop_city == fac_city:
                    score = 35

            # Name matching — boost or create score if facility name overlaps customer name
            if cust_name_words and fac.name:
                fac_name_words = set(fac.name.lower().split()) - {"apartments", "apartment", "apts", "apt", "the", "at", "of", "and", "llc", "inc"}
                overlap = cust_name_words & fac_name_words
                if overlap and len(overlap) >= 1:
                    score = max(score, 30) + min(len(overlap) * 15, 30)

            if score >= 30:
                scored.append((score, fac))

        scored.sort(key=lambda x: -x[0])

        # Get inspection stats for top results
        suggestions = []
        for score, fac in scored[:5]:
            stats = await self.db.execute(
                select(
                    func.count(Inspection.id),
                    func.count(InspectionViolation.id),
                    func.max(Inspection.inspection_date),
                )
                .select_from(Inspection)
                .outerjoin(InspectionViolation, InspectionViolation.inspection_id == Inspection.id)
                .where(Inspection.facility_id == fac.id)
            )
            stat_row = stats.one()
            suggestions.append({
                "facility_id": fac.id,
                "facility_name": fac.name,
                "street_address": fac.street_address,
                "city": fac.city,
                "score": score,
                "total_inspections": stat_row[0] or 0,
                "total_violations": stat_row[1] or 0,
                "last_inspection_date": stat_row[2],
            })

        return suggestions

    async def unmatch_property(self, property_id: str, organization_id: str):
        """Remove EMD match from a property and clear FA/PR numbers."""
        # Find and unlink facility
        result = await self.db.execute(
            select(InspectionFacility).where(InspectionFacility.matched_property_id == property_id)
        )
        for fac in result.scalars().all():
            fac.matched_property_id = None
            fac.matched_at = None

        # Clear FA number on property
        prop_result = await self.db.execute(
            select(Property).where(Property.id == property_id, Property.organization_id == organization_id)
        )
        prop = prop_result.scalar_one_or_none()
        if prop:
            prop.emd_fa_number = None

        # Clear PR numbers on water features
        wf_result = await self.db.execute(
            select(WaterFeature).where(WaterFeature.property_id == property_id)
        )
        for wf in wf_result.scalars().all():
            wf.emd_pr_number = None

        await self.db.flush()

    # --- Queries ---

    async def list_facilities(
        self,
        search: Optional[str] = None,
        matched_only: bool = False,
        limit: int = 50,
        offset: int = 0,
        sort: str = "name",
    ) -> tuple[list[dict], int]:
        """List EMD water features — one row per (facility, permit_id).

        Each facility with multiple water features (PRs) appears as separate rows.
        Stats and closure are per water feature.
        """
        # Query: group inspections by (facility_id, program_identifier) with stats
        # program_identifier stays consistent across years; permit_id can change
        wf_query = (
            select(
                Inspection.facility_id,
                Inspection.program_identifier,
                func.count(Inspection.id).label("total_inspections"),
                func.max(Inspection.inspection_date).label("last_inspection_date"),
                func.max(Inspection.permit_id).label("permit_id"),
            )
            .where(Inspection.program_identifier.isnot(None))
            .group_by(Inspection.facility_id, Inspection.program_identifier)
        )
        wf_sq = wf_query.subquery()

        # Join to facility for name/address and apply filters
        query = (
            select(
                InspectionFacility,
                wf_sq.c.permit_id,
                wf_sq.c.program_identifier,
                wf_sq.c.total_inspections,
                wf_sq.c.last_inspection_date,
            )
            .join(wf_sq, InspectionFacility.id == wf_sq.c.facility_id)
        )

        if search:
            query = query.where(
                InspectionFacility.name.ilike(f"%{search}%")
                | InspectionFacility.street_address.ilike(f"%{search}%")
                | InspectionFacility.facility_id.ilike(f"%{search}%")
            )
        if matched_only:
            query = query.where(InspectionFacility.matched_property_id.isnot(None))

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Sort
        if sort == "violations":
            query = query.order_by(InspectionFacility.name, wf_sq.c.program_identifier)
        elif sort == "last_inspection":
            query = query.order_by(desc(wf_sq.c.last_inspection_date))
        else:
            query = query.order_by(InspectionFacility.name, wf_sq.c.program_identifier)

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        rows = result.all()

        # Collect keys for batch lookups
        wf_keys = [(row[0].id, row.program_identifier) for row in rows]

        # Batch: violation count per (facility_id, program_identifier)
        viol_map: dict[tuple, int] = {}
        for fac_id, prog in wf_keys:
            viol_result = await self.db.execute(
                select(func.count(InspectionViolation.id))
                .join(Inspection, InspectionViolation.inspection_id == Inspection.id)
                .where(
                    Inspection.facility_id == fac_id,
                    Inspection.program_identifier == prog,
                )
            )
            viol_map[(fac_id, prog)] = viol_result.scalar() or 0

        # Batch: closure per (facility, program_identifier) — latest inspection's violations
        closure_map: dict[tuple, bool] = {}
        closure_reasons_map: dict[tuple, list[str]] = {}
        for fac_id, prog in wf_keys:
            latest_result = await self.db.execute(
                select(Inspection.id)
                .where(
                    Inspection.facility_id == fac_id,
                    Inspection.program_identifier == prog,
                )
                .order_by(desc(Inspection.inspection_date))
                .limit(1)
            )
            latest_id = latest_result.scalar()
            if latest_id:
                cv_result = await self.db.execute(
                    select(InspectionViolation.violation_code, InspectionViolation.violation_title)
                    .where(
                        InspectionViolation.inspection_id == latest_id,
                        InspectionViolation.observations.op("~*")(r"MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE"),
                    )
                )
                reasons = []
                for vrow in cv_result.all():
                    code = (vrow.violation_code or "").strip().lower()
                    label = VIOLATION_LABELS.get(code, vrow.violation_title or "Violation")
                    if label not in reasons:
                        reasons.append(label)
                if reasons:
                    closure_map[(fac_id, prog)] = True
                    closure_reasons_map[(fac_id, prog)] = reasons

        items = []
        for row in rows:
            fac = row[0]
            prog = row.program_identifier or "POOL"
            key = (fac.id, prog)
            items.append({
                "id": fac.id,
                "name": fac.name,
                "street_address": fac.street_address,
                "city": fac.city,
                "facility_id": fac.facility_id,
                "facility_type": fac.facility_type,
                "program_identifier": prog,
                "permit_id": row.permit_id,
                "matched_property_id": fac.matched_property_id,
                "total_inspections": row.total_inspections or 0,
                "total_violations": viol_map.get(key, 0),
                "last_inspection_date": row.last_inspection_date,
                "is_closed": closure_map.get(key, False),
                "closure_reasons": closure_reasons_map.get(key, []),
            })

        return items, total

    async def get_facility_detail(self, facility_id: str) -> Optional[dict]:
        """Get facility with full inspection history."""
        result = await self.db.execute(
            select(InspectionFacility).where(InspectionFacility.id == facility_id)
        )
        facility = result.scalar_one_or_none()
        if not facility:
            return None

        # Get inspections with violations
        result = await self.db.execute(
            select(Inspection)
            .where(Inspection.facility_id == facility_id)
            .options(selectinload(Inspection.violations), selectinload(Inspection.equipment))
            .order_by(desc(Inspection.inspection_date))
        )
        inspections = result.scalars().all()

        # Get matched property info + WF names
        matched_property_address = None
        matched_customer_name = None
        matched_customer_id = None
        matched_bow_names: dict[str, str] = {}  # bow_type -> bow_name
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
                matched_customer_id = row[1].id

            # Get WF names from the matched property
            from src.models.water_feature import WaterFeature
            bow_result = await self.db.execute(
                select(WaterFeature.water_type, WaterFeature.name)
                .where(WaterFeature.property_id == facility.matched_property_id)
            )
            for bow_row in bow_result.all():
                bow_type = (bow_row.water_type or "pool").lower()
                if bow_row.name:
                    matched_bow_names[bow_type] = bow_row.name

        total_violations = sum(i.total_violations for i in inspections)
        last_date = inspections[0].inspection_date if inspections else None

        # Build programs summary (distinct PRs with stats)
        closure_re = __import__("re").compile(r"MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE", __import__("re").IGNORECASE)
        programs: dict[str, dict] = {}
        for insp in inspections:
            pr = insp.permit_id or "unknown"
            if pr not in programs:
                programs[pr] = {
                    "permit_id": insp.permit_id,
                    "program_identifier": insp.program_identifier or "POOL",
                    "total_inspections": 0,
                    "total_violations": 0,
                    "last_inspection_date": None,
                    "is_closed": False,
                }
            p = programs[pr]
            p["total_inspections"] += 1
            p["total_violations"] += insp.total_violations
            if not p["last_inspection_date"] or (insp.inspection_date and insp.inspection_date > p["last_inspection_date"]):
                p["last_inspection_date"] = insp.inspection_date
                # Check closure on the latest inspection for this PR
                if insp.violations:
                    p["is_closed"] = any(
                        v.observations and closure_re.search(v.observations)
                        for v in insp.violations
                    )

        return {
            "facility": facility,
            "inspections": inspections,
            "programs": list(programs.values()),
            "total_inspections": len(inspections),
            "total_violations": total_violations,
            "last_inspection_date": last_date,
            "matched_property_address": matched_property_address,
            "matched_customer_name": matched_customer_name,
            "matched_customer_id": matched_customer_id,
            "matched_bow_names": matched_bow_names,
        }

    async def get_facility_inspections(self, facility_id: str) -> list[Inspection]:
        """Get all inspections for a facility."""
        result = await self.db.execute(
            select(Inspection)
            .where(Inspection.facility_id == facility_id)
            .options(selectinload(Inspection.violations))
            .order_by(desc(Inspection.inspection_date))
        )
        return result.scalars().all()

    async def get_facility_equipment(self, facility_id: str, permit_id: str | None = None) -> Optional[InspectionEquipment]:
        """Get the latest equipment data for a facility, optionally filtered by permit_id."""
        query = (
            select(InspectionEquipment)
            .join(Inspection, InspectionEquipment.inspection_id == Inspection.id)
            .where(InspectionEquipment.facility_id == facility_id)
        )
        if permit_id:
            query = query.where(Inspection.permit_id == permit_id)
        result = await self.db.execute(
            query.order_by(desc(Inspection.inspection_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_property_inspections(self, property_id: str) -> list[Inspection]:
        """Get inspections for a matched property."""
        result = await self.db.execute(
            select(Inspection)
            .join(InspectionFacility, Inspection.facility_id == InspectionFacility.id)
            .where(InspectionFacility.matched_property_id == property_id)
            .options(selectinload(Inspection.violations))
            .order_by(desc(Inspection.inspection_date))
        )
        return result.scalars().all()

    # --- Dashboard ---

    async def get_dashboard(self) -> dict:
        """Build the operations dashboard: inspections this week, alerts, fresh leads, trending worse."""
        now = date.today()
        seven_days_ago = now - timedelta(days=7)
        ninety_days_ago = now - timedelta(days=90)

        # --- my_inspections_this_week: matched facilities inspected in last 7 days ---
        my_insp_result = await self.db.execute(
            select(Inspection, InspectionFacility)
            .join(InspectionFacility, Inspection.facility_id == InspectionFacility.id)
            .where(
                InspectionFacility.matched_property_id.isnot(None),
                Inspection.inspection_date >= seven_days_ago,
            )
            .order_by(desc(Inspection.inspection_date))
        )
        my_inspections = []
        my_insp_ids = []
        my_insp_data = []
        for insp, fac in my_insp_result.all():
            my_insp_ids.append(insp.id)
            my_insp_data.append((insp, fac))

        # Derive closure from violations, not the boolean
        my_closure_set: set[str] = set()
        if my_insp_ids:
            closure_viols = await self.db.execute(
                select(InspectionViolation.inspection_id).where(
                    InspectionViolation.inspection_id.in_(my_insp_ids),
                    InspectionViolation.observations.op("~*")(r"MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE"),
                ).distinct()
            )
            my_closure_set = {r.inspection_id for r in closure_viols.all()}

        for insp, fac in my_insp_data:
            my_inspections.append({
                "facility_name": fac.name,
                "facility_id": fac.id,
                "inspection_date": str(insp.inspection_date) if insp.inspection_date else None,
                "total_violations": insp.total_violations or 0,
                "major_violations": insp.major_violations or 0,
                "closure_required": insp.id in my_closure_set,
                "is_matched": True,
            })

        # --- season_alerts: repeat violations, closures, unresolved from last season ---
        season_alerts = []

        # Get all matched facility IDs
        matched_result = await self.db.execute(
            select(InspectionFacility.id, InspectionFacility.name)
            .where(InspectionFacility.matched_property_id.isnot(None))
        )
        matched_facilities = {row.id: row.name for row in matched_result.all()}

        if matched_facilities:
            matched_ids = list(matched_facilities.keys())

            # Recent closures (last 90 days) for matched facilities
            # Derive from violations, not the closure_required boolean
            closure_result = await self.db.execute(
                select(InspectionViolation.facility_id, Inspection.inspection_date)
                .join(Inspection, InspectionViolation.inspection_id == Inspection.id)
                .where(
                    InspectionViolation.facility_id.in_(matched_ids),
                    InspectionViolation.observations.op("~*")(r"MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE"),
                    Inspection.inspection_date >= ninety_days_ago,
                )
                .distinct()
                .order_by(desc(Inspection.inspection_date))
            )
            for row in closure_result.all():
                fac_name = matched_facilities.get(row.facility_id, "Unknown")
                season_alerts.append({
                    "facility_name": fac_name,
                    "facility_id": row.facility_id,
                    "alert_type": "recent_closure",
                    "description": f"Closure required on {row.inspection_date}",
                    "last_inspection_date": str(row.inspection_date) if row.inspection_date else None,
                })

            # Repeat violations: same violation_code in 2+ of last 3 inspections per matched facility
            for fac_id in matched_ids:
                last3_result = await self.db.execute(
                    select(Inspection.id)
                    .where(Inspection.facility_id == fac_id)
                    .order_by(desc(Inspection.inspection_date))
                    .limit(3)
                )
                last3_ids = [r.id for r in last3_result.all()]
                if len(last3_ids) < 2:
                    continue

                viol_result = await self.db.execute(
                    select(
                        InspectionViolation.violation_code,
                        func.count(InspectionViolation.id).label("cnt"),
                    )
                    .where(
                        InspectionViolation.inspection_id.in_(last3_ids),
                        InspectionViolation.violation_code.isnot(None),
                    )
                    .group_by(InspectionViolation.violation_code)
                    .having(func.count(InspectionViolation.id) >= 2)
                )
                for vrow in viol_result.all():
                    code = (vrow.violation_code or "").strip().lower()
                    label = VIOLATION_LABELS.get(code, vrow.violation_code or "Violation")
                    fac_name = matched_facilities.get(fac_id, "Unknown")
                    # Get last inspection date for context
                    last_insp = await self.db.execute(
                        select(func.max(Inspection.inspection_date))
                        .where(Inspection.facility_id == fac_id)
                    )
                    last_date = last_insp.scalar()
                    season_alerts.append({
                        "facility_name": fac_name,
                        "facility_id": fac_id,
                        "alert_type": "repeat_violation",
                        "description": f"{label} flagged in {vrow.cnt} of last {len(last3_ids)} inspections",
                        "last_inspection_date": str(last_date) if last_date else None,
                    })

        # --- fresh_leads: unmatched facilities inspected in last 7 days with violations ---
        leads_result = await self.db.execute(
            select(InspectionFacility, Inspection)
            .join(Inspection, Inspection.facility_id == InspectionFacility.id)
            .where(
                InspectionFacility.matched_property_id.is_(None),
                Inspection.inspection_date >= seven_days_ago,
                Inspection.total_violations > 0,
            )
            .order_by(desc(Inspection.total_violations))
        )
        fresh_leads = []
        seen_lead_ids = set()
        lead_insp_ids = []
        lead_data = []
        for fac, insp in leads_result.all():
            if fac.id in seen_lead_ids:
                continue
            seen_lead_ids.add(fac.id)
            lead_insp_ids.append(insp.id)
            lead_data.append((fac, insp))

        # Derive closure from violations
        lead_closure_set: set[str] = set()
        if lead_insp_ids:
            lc_result = await self.db.execute(
                select(InspectionViolation.inspection_id).where(
                    InspectionViolation.inspection_id.in_(lead_insp_ids),
                    InspectionViolation.observations.op("~*")(r"MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE"),
                ).distinct()
            )
            lead_closure_set = {r.inspection_id for r in lc_result.all()}

        for fac, insp in lead_data:
            fresh_leads.append({
                "facility_name": fac.name,
                "facility_id": fac.id,
                "address": f"{fac.street_address or ''}{', ' + fac.city if fac.city else ''}",
                "inspection_date": str(insp.inspection_date) if insp.inspection_date else None,
                "total_violations": insp.total_violations or 0,
                "closure_required": insp.id in lead_closure_set,
            })

        # --- trending_worse: facilities where most recent inspection has MORE violations than previous ---
        trending_worse = []
        # Get all facilities with at least 2 inspections
        fac_with_multi = await self.db.execute(
            select(Inspection.facility_id)
            .group_by(Inspection.facility_id)
            .having(func.count(Inspection.id) >= 2)
        )
        for row in fac_with_multi.all():
            fac_id = row.facility_id
            last2_result = await self.db.execute(
                select(Inspection.total_violations, Inspection.inspection_date)
                .where(Inspection.facility_id == fac_id)
                .order_by(desc(Inspection.inspection_date))
                .limit(2)
            )
            last2 = last2_result.all()
            if len(last2) < 2:
                continue
            recent_v = last2[0].total_violations or 0
            previous_v = last2[1].total_violations or 0
            if recent_v > previous_v and recent_v > 0:
                # Get facility name
                fac_result = await self.db.execute(
                    select(InspectionFacility.name).where(InspectionFacility.id == fac_id)
                )
                fac_name = fac_result.scalar() or "Unknown"
                trending_worse.append({
                    "facility_name": fac_name,
                    "facility_id": fac_id,
                    "recent_violations": recent_v,
                    "previous_violations": previous_v,
                    "trend": "increasing",
                })

        trending_worse.sort(key=lambda x: x["recent_violations"] - x["previous_violations"], reverse=True)

        return {
            "my_inspections_this_week": my_inspections,
            "season_alerts": season_alerts,
            "fresh_leads": fresh_leads,
            "trending_worse": trending_worse,
        }

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
                InspectionViolation.facility_id,
                func.count(InspectionViolation.id).label("violation_count"),
            )
            .join(Inspection, InspectionViolation.inspection_id == Inspection.id)
            .where(Inspection.inspection_date >= cutoff)
            .group_by(InspectionViolation.facility_id)
            .having(func.count(InspectionViolation.id) >= min_violations)
            .subquery()
        )

        result = await self.db.execute(
            select(
                InspectionFacility.id,
                InspectionFacility.name,
                InspectionFacility.street_address,
                InspectionFacility.city,
                InspectionFacility.matched_property_id,
                recent_violations.c.violation_count,
            )
            .join(recent_violations, InspectionFacility.id == recent_violations.c.facility_id)
            .order_by(desc(recent_violations.c.violation_count))
        )
        rows = result.all()

        leads = []
        for row in rows:
            # Get inspection count and last date
            insp_result = await self.db.execute(
                select(
                    func.count(Inspection.id),
                    func.max(Inspection.inspection_date),
                )
                .where(
                    Inspection.facility_id == row.id,
                    Inspection.inspection_date >= cutoff,
                )
            )
            insp_row = insp_result.first()

            # Count major violations
            major_result = await self.db.execute(
                select(func.count(InspectionViolation.id))
                .join(Inspection, InspectionViolation.inspection_id == Inspection.id)
                .where(
                    InspectionViolation.facility_id == row.id,
                    InspectionViolation.is_major_violation == True,
                    Inspection.inspection_date >= cutoff,
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

    # --- Sync equipment to WF ---

    async def sync_equipment_to_bow(self, facility_id: str) -> Optional[dict]:
        """Copy latest EMD equipment data to the matched property's primary WF."""
        from src.models.water_feature import WaterFeature

        # Get facility with match
        result = await self.db.execute(
            select(InspectionFacility).where(InspectionFacility.id == facility_id)
        )
        facility = result.scalar_one_or_none()
        if not facility or not facility.matched_property_id:
            return None

        # Get latest equipment
        equipment = await self.get_facility_equipment(facility_id)
        if not equipment:
            return None

        # Get primary WF for the property
        result = await self.db.execute(
            select(WaterFeature).where(
                WaterFeature.property_id == facility.matched_property_id,
                WaterFeature.is_primary == True,
            )
        )
        wf = result.scalar_one_or_none()
        if not wf:
            return None

        # Sync pool specs
        updated = {}
        if equipment.pool_capacity_gallons and not wf.pool_gallons:
            wf.pool_gallons = equipment.pool_capacity_gallons
            updated["pool_gallons"] = equipment.pool_capacity_gallons

        await self.db.flush()
        return {"wf_id": wf.id, "updated_fields": updated}

    # --- Helpers ---

    @staticmethod
    @staticmethod
    def _extract_program_address(prog_id: str | None) -> str | None:
        """Pull the address suffix from a program_identifier like
        'POOL @ 4440 OAK HOLLOW DR'. Returns None if no '@' delimiter or
        if the suffix doesn't start with a digit (street number).
        """
        if not prog_id or "@" not in prog_id:
            return None
        suffix = prog_id.split("@", 1)[1].strip()
        if not suffix or not suffix[0].isdigit():
            return None
        return suffix

    @staticmethod
    def _parse_address(address: str) -> tuple[str, str, str, str]:
        """Parse an address string into (street, city, state, zip).

        Handles two scraper output formats:
          - 3-part legacy: "street, city, CA zip"
          - 2-part current: "street  city, CA zip" (street and city joined by 2+ spaces)
        """
        if not address or address == "Unknown":
            return ("", "", "CA", "")

        parts = [p.strip() for p in address.split(",")]

        # 3-part legacy format
        if len(parts) >= 3:
            street = parts[0]
            city = parts[1]
            sz_parts = parts[2].split()
            state = "CA"
            zip_code = ""
            if len(sz_parts) >= 2:
                state = sz_parts[0]
                zip_code = sz_parts[1]
            elif len(sz_parts) == 1:
                if sz_parts[0][0].isdigit():
                    zip_code = sz_parts[0]
                else:
                    state = sz_parts[0]
            return (street, city, state, zip_code)

        # 2-part current format: "street  city, ST zip"
        if len(parts) == 2:
            sz_match = re.match(r"^([A-Z]{2})\s+([\d-]+)$", parts[1])
            if sz_match:
                state = sz_match.group(1)
                zip_code = sz_match.group(2)
                # Split parts[0] on the last run of 2+ spaces to separate street from city
                sc_match = re.match(r"^(.+?)\s{2,}(\S.*)$", parts[0])
                if sc_match:
                    return (sc_match.group(1).strip(), sc_match.group(2).strip(), state, zip_code)
                # No double-space delimiter — fall back to the last token as city
                tokens = parts[0].split()
                if len(tokens) >= 2:
                    return (" ".join(tokens[:-1]), tokens[-1], state, zip_code)
                return (parts[0], "", state, zip_code)
            # parts[1] doesn't look like state+zip — assume it's the city
            return (parts[0], parts[1], "CA", "")

        # 1-part fallback
        return (parts[0] if parts else "", "", "CA", "")

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
        # Standardize abbreviations (both directions)
        addr = addr.replace(" street", " st").replace(" avenue", " ave")
        addr = addr.replace(" boulevard", " blvd").replace(" drive", " dr")
        addr = addr.replace(" road", " rd").replace(" lane", " ln")
        addr = addr.replace(" court", " ct").replace(" place", " pl")
        addr = addr.replace(" parkway", " pkwy").replace(" circle", " cir")
        addr = addr.replace(" terrace", " ter").replace(" way", " wy")
        addr = addr.replace(" south ", " s ").replace(" north ", " n ")
        addr = addr.replace(" east ", " e ").replace(" west ", " w ")
        # Remove extra spaces
        addr = re.sub(r"\s+", " ", addr).strip()
        return addr
