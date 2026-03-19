#!/usr/bin/env python3
"""Backfill program_identifier on EMD inspections from their PDFs.

Each inspection PDF has its own Program Identifier (POOL, SPA, LAP POOL, etc.)
that tells you which body of water was inspected. This belongs on the inspection,
not the facility (a facility can have both pool and spa).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from src.core.database import get_db_context
from src.models.emd_inspection import EMDInspection
from src.services.emd.pdf_extractor import EMDPDFExtractor


async def main():
    extractor = EMDPDFExtractor()
    updated = 0
    no_pdf = 0
    no_prog = 0
    already = 0

    async with get_db_context() as db:
        result = await db.execute(
            select(EMDInspection).where(
                EMDInspection.pdf_path.isnot(None),
                EMDInspection.pdf_path.notlike("/mnt%"),
                EMDInspection.program_identifier.is_(None),
            )
        )
        inspections = result.scalars().all()
        print(f"Inspections to process: {len(inspections)}")

        for i, insp in enumerate(inspections):
            pdf_path = insp.pdf_path
            if not os.path.isabs(pdf_path):
                pdf_path = os.path.join(os.path.dirname(__file__), "..", pdf_path)

            if not os.path.exists(pdf_path):
                no_pdf += 1
                continue

            text = extractor.extract_text(pdf_path)
            prog = extractor._extract_program_identifier(text)
            if prog:
                insp.program_identifier = prog
                updated += 1
            else:
                no_prog += 1

            if (i + 1) % 100 == 0:
                await db.flush()
                print(f"  ... {i + 1}/{len(inspections)} ({updated} updated)")

        await db.flush()

    print(f"\nDone. Updated: {updated} | No PDF on disk: {no_pdf} | No prog in PDF: {no_prog}")


if __name__ == "__main__":
    asyncio.run(main())
