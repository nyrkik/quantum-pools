"""Phase C of inspection scraper recovery — rebuild broken stub facilities
from existing local PDFs.

Background: see docs/inspection-scraper-recovery.md.

What this does:
  1. Find all broken stub facilities (facility_id IS NULL OR '').
  2. Clear matched_property_id from broken stubs (auto_match re-runs at end).
  3. For each stub, walk its inspections. For each inspection with a PDF on
     disk, extract the canonical Establishment ID (FA####) and clean
     facility metadata.
  4. Group the stub's inspections by FA####.
  5. For each FA#### group:
       - Find or create a proper inspection_facility row using the most
         recent PDF's name + structured address.
       - Reassign all inspections in this group (and their violations and
         equipment rows) to the new facility.
  6. After splitting, if the stub has 0 remaining inspections, delete it.
     If it has unrecoverable orphans (no PDF / no extractable FA####), leave
     it in place.
  7. Re-run auto_match_facilities for the org.

Run from project root:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python app/scripts/rebuild_broken_facilities.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python app/scripts/rebuild_broken_facilities.py
"""

import asyncio
import logging
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update, delete

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.models.inspection_facility import InspectionFacility
from src.models.inspection_violation import InspectionViolation
from src.models.inspection_equipment import InspectionEquipment
from src.models.organization import Organization
from src.services.inspection.pdf_extractor import EMDPDFExtractor
from src.services.inspection.service import InspectionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_pdf(path: str | None) -> str | None:
    """PDFs are stored with paths like
    '/srv/quantumpools/app/scripts/../uploads/emd/2025/<id>.pdf'.
    Resolve to canonical absolute and confirm existence.
    """
    if not path:
        return None
    try:
        resolved = str(Path(path).resolve())
    except Exception:
        return None
    return resolved if os.path.exists(resolved) else None


async def main(dry_run: bool):
    extractor = EMDPDFExtractor()

    async with get_db_context() as db:
        # 1. Find broken stubs
        broken_result = await db.execute(
            select(InspectionFacility).where(
                (InspectionFacility.facility_id.is_(None))
                | (InspectionFacility.facility_id == "")
            )
        )
        broken_stubs = broken_result.scalars().all()
        logger.info(f"Found {len(broken_stubs)} broken stub facilities")

        if not broken_stubs:
            logger.info("Nothing to do.")
            return

        # 2. Clear matched_property_id from broken stubs (re-runs auto_match at end)
        previously_matched = [(s.id, s.matched_property_id) for s in broken_stubs if s.matched_property_id]
        logger.info(f"  {len(previously_matched)} broken stubs had a matched_property_id (will re-run auto_match)")
        for stub in broken_stubs:
            stub.matched_property_id = None
            stub.matched_at = None

        # Track stats
        stats = {
            "stubs_processed": 0,
            "stubs_deleted": 0,
            "stubs_kept_with_orphans": 0,
            "facilities_created": 0,
            "facilities_reused": 0,
            "inspections_reassigned": 0,
            "violations_reassigned": 0,
            "equipment_reassigned": 0,
            "inspections_unrecoverable": 0,
            "pdf_extract_failures": 0,
        }

        # Cache: FA#### -> facility row (created during this run)
        new_facility_cache: dict[str, InspectionFacility] = {}

        for stub in broken_stubs:
            stats["stubs_processed"] += 1
            logger.info(f"\nStub {stub.id[:8]} '{stub.name}':")

            # Walk inspections
            insp_result = await db.execute(
                select(Inspection).where(Inspection.facility_id == stub.id)
            )
            inspections = insp_result.scalars().all()
            logger.info(f"  {len(inspections)} inspections")

            # Group by extracted FA####
            groups: dict[str, list[tuple[Inspection, dict]]] = defaultdict(list)
            orphans: list[Inspection] = []

            for insp in inspections:
                pdf_path = _resolve_pdf(insp.pdf_path)
                if not pdf_path:
                    orphans.append(insp)
                    continue
                try:
                    pdf_data = extractor.extract_all(pdf_path)
                except Exception as e:
                    logger.warning(f"    PDF extract failed for {insp.inspection_id}: {e}")
                    stats["pdf_extract_failures"] += 1
                    orphans.append(insp)
                    continue

                fa = pdf_data.get("facility_id")
                if not fa:
                    orphans.append(insp)
                    continue

                groups[fa].append((insp, pdf_data))

            stats["inspections_unrecoverable"] += len(orphans)
            if orphans:
                logger.info(f"  {len(orphans)} unrecoverable inspections (no PDF / no FA####) — left on stub")

            # Process each group
            for fa, group in groups.items():
                # Sort by inspection_date desc to use most recent PDF for facility metadata
                group.sort(key=lambda x: x[0].inspection_date or x[0].created_at, reverse=True)
                most_recent_insp, most_recent_pdf = group[0]

                # Find or create the proper facility for this FA####
                facility = new_facility_cache.get(fa)
                if facility is None:
                    existing = await db.execute(
                        select(InspectionFacility).where(InspectionFacility.facility_id == fa)
                    )
                    facility = existing.scalar_one_or_none()

                if facility is None:
                    facility = InspectionFacility(
                        id=str(uuid.uuid4()),
                        facility_id=fa,
                        name=most_recent_pdf.get("facility_name") or stub.name,
                        street_address=most_recent_pdf.get("facility_address") or "",
                        city=most_recent_pdf.get("facility_city") or "",
                        state="CA",
                        zip_code=most_recent_pdf.get("facility_zip") or "",
                        permit_holder=most_recent_pdf.get("permit_holder"),
                        phone=most_recent_pdf.get("phone_number"),
                    )
                    db.add(facility)
                    await db.flush()
                    stats["facilities_created"] += 1
                    new_facility_cache[fa] = facility
                    logger.info(
                        f"  + Created facility {fa} '{facility.name}' "
                        f"({facility.street_address}, {facility.city} {facility.zip_code})"
                    )
                else:
                    stats["facilities_reused"] += 1
                    new_facility_cache[fa] = facility
                    logger.info(f"  ~ Reusing existing facility {fa} '{facility.name}'")

                # Reassign all inspections in this group
                insp_ids = [i.id for i, _ in group]

                # Inspections
                await db.execute(
                    update(Inspection)
                    .where(Inspection.id.in_(insp_ids))
                    .values(facility_id=facility.id)
                )
                stats["inspections_reassigned"] += len(insp_ids)

                # Violations (also have facility_id FK)
                viol_count_result = await db.execute(
                    select(InspectionViolation).where(InspectionViolation.inspection_id.in_(insp_ids))
                )
                viol_rows = viol_count_result.scalars().all()
                for v in viol_rows:
                    v.facility_id = facility.id
                stats["violations_reassigned"] += len(viol_rows)

                # Equipment (also have facility_id FK)
                equip_result = await db.execute(
                    select(InspectionEquipment).where(InspectionEquipment.inspection_id.in_(insp_ids))
                )
                equip_rows = equip_result.scalars().all()
                for e in equip_rows:
                    e.facility_id = facility.id
                stats["equipment_reassigned"] += len(equip_rows)

                logger.info(
                    f"    -> {len(insp_ids)} inspections, {len(viol_rows)} violations, "
                    f"{len(equip_rows)} equipment rows reassigned"
                )

            # Delete stub if it has no remaining inspections
            await db.flush()
            remaining = await db.execute(
                select(Inspection.id).where(Inspection.facility_id == stub.id).limit(1)
            )
            if not remaining.first():
                await db.delete(stub)
                stats["stubs_deleted"] += 1
                logger.info(f"  - Deleted empty stub {stub.id[:8]}")
            else:
                stats["stubs_kept_with_orphans"] += 1
                logger.info(f"  = Stub {stub.id[:8]} kept (has unrecoverable inspections)")

        # 7. Re-run auto_match for the org
        logger.info("\nRe-running auto_match_facilities...")
        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org:
            svc = InspectionService(db)
            match_result = await svc.auto_match_facilities(org.id)
            logger.info(
                f"  auto_match: {match_result.get('matched', 0)} new matches, "
                f"{match_result.get('removed', 0)} removed, "
                f"{match_result.get('total_unmatched', 0)} still unmatched"
            )

        # Commit or rollback
        if dry_run:
            logger.info("\nDRY RUN — rolling back")
            await db.rollback()
        else:
            await db.commit()
            logger.info("\nCommitted.")

        # Print final stats
        logger.info("\n=== STATS ===")
        for k, v in stats.items():
            logger.info(f"  {k}: {v}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry))
