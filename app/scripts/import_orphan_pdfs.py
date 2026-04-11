"""Import orphan inspection PDFs (files on disk that have no matching DB row)
back into the inspections table.

Background: an audit on 2026-04-11 found 21 PDFs in uploads/emd/ and
uploads/inspection/ that have no corresponding `inspections` row. The PDFs
contain everything needed to reconstruct the row (FA####, PR####, date,
address, violations, equipment) — no portal scraping required.

Each orphan is processed via the existing InspectionService.process_facility
pipeline, which extracts the PDF and creates the facility + inspection +
violations + equipment in one transaction.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/import_orphan_pdfs.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/import_orphan_pdfs.py
"""

import asyncio
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.inspection import Inspection
from src.services.inspection.service import InspectionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

UUID_RE = re.compile(
    r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$",
    re.IGNORECASE,
)
UPLOADS_ROOTS = [
    Path("/srv/quantumpools/app/uploads/emd"),
    Path("/srv/quantumpools/app/uploads/inspection"),
]


def collect_pdfs() -> dict[str, Path]:
    """Walk the upload trees and return {INSPECTION_ID_UPPER: path}.

    If the same inspection_id appears in multiple locations, the first one
    found wins (we'll dedupe filesystem-side as a separate cleanup step).
    """
    out: dict[str, Path] = {}
    for root in UPLOADS_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.pdf"):
            stem = p.stem
            # Skip test files and anything that doesn't look like a UUID
            if not UUID_RE.match(stem):
                continue
            key = stem.upper()
            out.setdefault(key, p)
    return out


async def main(dry_run: bool):
    pdfs = collect_pdfs()
    logger.info(f"Found {len(pdfs)} unique inspection PDFs across upload trees")

    async with get_db_context() as db:
        rows = (await db.execute(
            select(Inspection.inspection_id).where(Inspection.inspection_id.isnot(None))
        )).all()
        db_ids = {r[0].upper() for r in rows if r[0]}

    orphan_ids = sorted(set(pdfs.keys()) - db_ids)
    logger.info(f"Orphans (PDFs with no DB row): {len(orphan_ids)}")

    if not orphan_ids:
        logger.info("Nothing to import.")
        return

    stats = {
        "processed": 0,
        "new_facility": 0,
        "new_inspection": 0,
        "skipped": 0,
        "errors": 0,
    }

    for iid in orphan_ids:
        pdf_path = pdfs[iid]
        # Build minimal fdata — process_facility will pull facility_name,
        # facility_id, address, etc. from the PDF.
        fdata = {
            "inspection_id": iid,
            "name": "",
            "address": "",
            "url": None,
            "pdf_url": None,
        }

        async with get_db_context() as db:
            svc = InspectionService(db)
            try:
                result = await svc.process_facility(fdata, pdf_path=str(pdf_path))
                stats["processed"] += 1
                if result == "new_facility":
                    stats["new_facility"] += 1
                elif result == "new_inspection":
                    stats["new_inspection"] += 1
                else:
                    stats["skipped"] += 1

                logger.info(f"  {iid[:8]}  {pdf_path.name}  -> {result}")

                if dry_run:
                    await db.rollback()
                else:
                    await db.commit()
            except Exception as e:
                logger.warning(f"  {iid[:8]}  FAILED: {e}")
                stats["errors"] += 1
                await db.rollback()

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    if dry_run:
        logger.info("(dry run — nothing committed)")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
