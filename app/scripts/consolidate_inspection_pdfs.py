"""Consolidate inspection PDFs into the canonical `uploads/inspection/<year>/`
tree, eliminating the duplicate `uploads/emd/<year>/` tree left over from
the EMD->Inspection rename.

Background: as of 2026-04-11 we have 2,108 PDFs in `uploads/emd/<year>/` and
459 in `uploads/inspection/<year>/`. Many appear in both trees (185 dupes).
DB rows point at a mix of both paths. This consolidates everything into
`uploads/inspection/` and rewrites DB pdf_path values to match.

Phases:
  1. Walk emd/ and ensure each file exists at the matching inspection/ path.
     Files that already exist at the destination must hash-match before the
     source copy is deleted (safety check).
  2. Rewrite DB pdf_path values from any emd/* path to the canonical
     inspection/* path (drops the legacy `scripts/..` indirection too).
  3. Verify every DB record's pdf_path resolves to an existing file.
  4. Optionally delete the now-empty emd/ tree (--delete-emd flag).

Run from /srv/quantumpools/app:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/consolidate_inspection_pdfs.py --dry-run
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/consolidate_inspection_pdfs.py
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/consolidate_inspection_pdfs.py --delete-emd
"""

import argparse
import asyncio
import hashlib
import logging
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from src.core.database import get_db_context
from src.models.inspection import Inspection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

EMD_ROOT = Path("/srv/quantumpools/app/uploads/emd")
INSPECTION_ROOT = Path("/srv/quantumpools/app/uploads/inspection")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def phase1_consolidate_files(dry_run: bool) -> dict:
    """Move/dedup files from emd/ into inspection/ (mirroring relative paths).

    Conflict policy: when the same UUID exists in both trees with different
    content, prefer the NEWER mtime (inspection/ versions are systematically
    newer re-downloads — verified empirically 2026-04-11). Older copies are
    deleted. If by chance the emd/ copy is newer, it overwrites inspection/.
    """
    stats = {
        "emd_files_seen": 0,
        "moved_to_inspection": 0,
        "deduped_identical": 0,
        "skipped_non_uuid": 0,
        "conflicts_resolved_keep_inspection": 0,
        "conflicts_resolved_keep_emd": 0,
    }
    if not EMD_ROOT.exists():
        logger.info("No emd/ tree, nothing to consolidate")
        return stats

    UUID_RE = re.compile(
        r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$",
        re.IGNORECASE,
    )

    for src in sorted(EMD_ROOT.rglob("*.pdf")):
        stats["emd_files_seen"] += 1

        if not UUID_RE.match(src.stem):
            logger.info(f"  skip non-UUID file: {src.relative_to(EMD_ROOT)}")
            stats["skipped_non_uuid"] += 1
            continue

        # Mirror the relative path under emd/ → same relative path under
        # inspection/. So emd/2025/foo.pdf → inspection/2025/foo.pdf, and
        # emd/scraped/foo.pdf → inspection/scraped/foo.pdf.
        rel = src.relative_to(EMD_ROOT)
        dst = INSPECTION_ROOT / rel

        if dst.exists():
            # Hash to determine if they're truly identical
            try:
                src_h = sha256(src)
                dst_h = sha256(dst)
            except Exception as e:
                logger.warning(f"  hash failed for {src.name}: {e}")
                continue
            if src_h == dst_h:
                stats["deduped_identical"] += 1
                if not dry_run:
                    src.unlink()
            else:
                # Same UUID, different content. Prefer the newer mtime.
                src_mtime = src.stat().st_mtime
                dst_mtime = dst.stat().st_mtime
                if dst_mtime >= src_mtime:
                    # inspection/ is newer (or same age) — keep it, delete emd/
                    stats["conflicts_resolved_keep_inspection"] += 1
                    if not dry_run:
                        src.unlink()
                else:
                    # emd/ is unexpectedly newer — overwrite inspection/
                    stats["conflicts_resolved_keep_emd"] += 1
                    logger.warning(
                        f"  emd/ newer than inspection/ for {src.name}: "
                        f"emd_mtime={src_mtime} inspection_mtime={dst_mtime} — overwriting"
                    )
                    if not dry_run:
                        shutil.move(str(src), str(dst))
        else:
            # Move src to dst
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
            stats["moved_to_inspection"] += 1
            if stats["moved_to_inspection"] % 200 == 0:
                logger.info(
                    f"  moved {stats['moved_to_inspection']} / consolidating..."
                )

    return stats


def normalize_pdf_path(p: str | None) -> str | None:
    """Rewrite a stored pdf_path so it points at the canonical
    /srv/quantumpools/app/uploads/inspection/<year>/<id>.pdf form, dropping
    the legacy `scripts/..` indirection and the `emd` directory name.
    """
    if not p:
        return p
    try:
        resolved = Path(p).resolve()
    except Exception:
        return p
    s = str(resolved)
    # Replace .../uploads/emd/ with .../uploads/inspection/
    if "/uploads/emd/" in s:
        s = s.replace("/uploads/emd/", "/uploads/inspection/")
    return s


async def phase2_rewrite_db_paths(dry_run: bool) -> dict:
    """Rewrite all inspection.pdf_path values to canonical paths."""
    stats = {"rows_seen": 0, "rows_updated": 0}
    async with get_db_context() as db:
        rows = (await db.execute(
            select(Inspection.id, Inspection.pdf_path)
            .where(Inspection.pdf_path.isnot(None))
        )).all()

        for row_id, pdf_path in rows:
            stats["rows_seen"] += 1
            new_path = normalize_pdf_path(pdf_path)
            if new_path != pdf_path:
                stats["rows_updated"] += 1
                if not dry_run:
                    await db.execute(
                        update(Inspection).where(Inspection.id == row_id).values(pdf_path=new_path)
                    )
        if not dry_run:
            await db.commit()
    return stats


async def phase3_verify(dry_run: bool) -> dict:
    """Confirm every DB pdf_path resolves to an existing file."""
    stats = {"rows_checked": 0, "missing_files": 0}
    missing_examples = []
    async with get_db_context() as db:
        rows = (await db.execute(
            select(Inspection.id, Inspection.inspection_id, Inspection.pdf_path)
            .where(Inspection.pdf_path.isnot(None))
        )).all()
        for row_id, iid, pdf_path in rows:
            stats["rows_checked"] += 1
            if not Path(pdf_path).exists():
                stats["missing_files"] += 1
                if len(missing_examples) < 10:
                    missing_examples.append((iid, pdf_path))
    if missing_examples:
        logger.warning("Sample DB rows with missing pdf_path on disk:")
        for iid, p in missing_examples:
            logger.warning(f"  {iid}: {p}")
    return stats


def phase4_delete_emd_tree(dry_run: bool, delete: bool) -> dict:
    """Delete the empty emd tree if --delete-emd was passed."""
    stats = {"deleted": False, "remaining_files": 0}
    if not EMD_ROOT.exists():
        return stats
    remaining = list(EMD_ROOT.rglob("*"))
    files = [p for p in remaining if p.is_file()]
    stats["remaining_files"] = len(files)
    if not delete:
        return stats
    if files:
        logger.warning(f"emd/ tree still has {len(files)} files — refusing to delete")
        return stats
    if not dry_run:
        shutil.rmtree(EMD_ROOT)
    stats["deleted"] = True
    return stats


async def main(dry_run: bool, delete_emd: bool):
    INSPECTION_ROOT.mkdir(parents=True, exist_ok=True)

    logger.info("=== Phase 1: consolidate files into uploads/inspection/ ===")
    p1 = phase1_consolidate_files(dry_run)
    for k, v in p1.items():
        logger.info(f"  {k}: {v}")

    logger.info("\n=== Phase 2: rewrite DB pdf_path values ===")
    p2 = await phase2_rewrite_db_paths(dry_run)
    for k, v in p2.items():
        logger.info(f"  {k}: {v}")

    logger.info("\n=== Phase 3: verify every DB pdf_path resolves ===")
    p3 = await phase3_verify(dry_run)
    for k, v in p3.items():
        logger.info(f"  {k}: {v}")

    logger.info("\n=== Phase 4: clean up emd/ tree ===")
    p4 = phase4_delete_emd_tree(dry_run, delete_emd)
    for k, v in p4.items():
        logger.info(f"  {k}: {v}")

    if dry_run:
        logger.info("\n(dry run — no filesystem moves, no DB commits)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delete-emd", action="store_true", help="Delete the empty emd/ tree after consolidation")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run, delete_emd=args.delete_emd))
