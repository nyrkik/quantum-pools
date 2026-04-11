"""Second-pass cleanup: deduplicate same UUID across multiple year directories
inside uploads/inspection/, and snap each file to the canonical year that
matches its inspection_date in the DB.

Background: same inspection_id appears in inspection/2024/, /2025/, /2026/
etc. due to a pre-2026-04-06 date-stamping bug that put files under the
search-date year instead of the inspection's actual year. The date column
was already corrected by backfill_inspection_dates.py, but the on-disk PDF
locations were never moved to match.

Strategy per duplicate UUID:
  1. Look up inspection_date from DB → canonical year directory
  2. If a copy exists at canonical → keep it, delete others
  3. If not → move newest-mtime copy to canonical, delete others
  4. Update DB pdf_path to canonical

For NON-duplicate UUIDs whose pdf_path year is wrong, also snap them.

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/dedupe_within_inspection.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/dedupe_within_inspection.py
"""

import argparse
import asyncio
import logging
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from src.core.database import get_db_context
from src.models.inspection import Inspection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

INSPECTION_ROOT = Path("/srv/quantumpools/app/uploads/inspection")
UUID_RE = re.compile(
    r"^([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})$",
    re.IGNORECASE,
)


def find_all_pdfs() -> dict[str, list[Path]]:
    """Return {UUID_UPPER: [paths...]}, only counting files whose stem is a UUID."""
    out: dict[str, list[Path]] = defaultdict(list)
    for p in INSPECTION_ROOT.rglob("*.pdf"):
        if UUID_RE.match(p.stem):
            out[p.stem.upper()].append(p)
    return out


async def main(dry_run: bool):
    pdfs = find_all_pdfs()
    logger.info(f"Found {len(pdfs)} unique inspection_ids on disk")

    # Load all DB records keyed by inspection_id (upper)
    async with get_db_context() as db:
        rows = (await db.execute(
            select(Inspection.id, Inspection.inspection_id, Inspection.inspection_date, Inspection.pdf_path)
            .where(Inspection.inspection_id.isnot(None))
        )).all()
        db_by_iid = {r[1].upper(): r for r in rows}

    stats = {
        "uuids_seen": 0,
        "single_copy_correct_year": 0,
        "single_copy_wrong_year_moved": 0,
        "duplicates_resolved": 0,
        "files_deleted": 0,
        "no_db_row": 0,
        "no_inspection_date": 0,
        "db_path_updated": 0,
    }

    for iid, paths in pdfs.items():
        stats["uuids_seen"] += 1
        db_row = db_by_iid.get(iid)
        if not db_row:
            stats["no_db_row"] += 1
            continue
        row_id, _, inspection_date, current_path = db_row
        if not inspection_date:
            stats["no_inspection_date"] += 1
            continue

        canonical_year = str(inspection_date.year)
        canonical = INSPECTION_ROOT / canonical_year / f"{iid}.pdf"

        if len(paths) == 1:
            existing = paths[0]
            if existing == canonical:
                stats["single_copy_correct_year"] += 1
                # Make sure DB matches
                if str(existing) != current_path:
                    if not dry_run:
                        async with get_db_context() as db:
                            await db.execute(update(Inspection).where(Inspection.id == row_id).values(pdf_path=str(existing)))
                            await db.commit()
                    stats["db_path_updated"] += 1
            else:
                # Single file in wrong year — move it
                logger.info(f"  move {existing.relative_to(INSPECTION_ROOT)} -> {canonical.relative_to(INSPECTION_ROOT)}")
                if not dry_run:
                    canonical.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(existing), str(canonical))
                stats["single_copy_wrong_year_moved"] += 1
                if not dry_run:
                    async with get_db_context() as db:
                        await db.execute(update(Inspection).where(Inspection.id == row_id).values(pdf_path=str(canonical)))
                        await db.commit()
                stats["db_path_updated"] += 1
            continue

        # Duplicates: pick winner = canonical if present, else newest mtime
        canonical_existing = next((p for p in paths if p == canonical), None)
        if canonical_existing:
            winner = canonical_existing
        else:
            winner = max(paths, key=lambda p: p.stat().st_mtime)
            logger.info(
                f"  dupe {iid[:8]}: no copy at canonical {canonical_year}, "
                f"using newest from {winner.parent.name}"
            )

        # Move winner to canonical if not already there
        if winner != canonical:
            if not dry_run:
                canonical.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(winner), str(canonical))
            winner_path_after = canonical
        else:
            winner_path_after = winner

        # Delete losers
        losers = [p for p in paths if p != winner and p != canonical]
        for loser in losers:
            if loser.exists():
                logger.info(f"  delete {loser.relative_to(INSPECTION_ROOT)}")
                if not dry_run:
                    loser.unlink()
                stats["files_deleted"] += 1

        stats["duplicates_resolved"] += 1
        if str(winner_path_after) != current_path:
            if not dry_run:
                async with get_db_context() as db:
                    await db.execute(update(Inspection).where(Inspection.id == row_id).values(pdf_path=str(winner_path_after)))
                    await db.commit()
            stats["db_path_updated"] += 1

    logger.info("\n=== STATS ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    if dry_run:
        logger.info("(dry run — nothing changed)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
