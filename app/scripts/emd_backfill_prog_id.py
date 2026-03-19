#!/usr/bin/env python3
"""Backfill program_identifier on EMD facilities from downloaded PDFs.

Reads each facility's most recent inspection PDF and extracts the Program Identifier
(POOL, SPA, LAP POOL, WADING POOL, etc.) to set on the facility record.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, desc
from src.core.database import get_db_context
from src.models.emd_facility import EMDFacility
from src.models.emd_inspection import EMDInspection
from src.services.emd.pdf_extractor import EMDPDFExtractor


async def main():
    extractor = EMDPDFExtractor()
    updated = 0
    no_pdf = 0
    no_prog = 0

    async with get_db_context() as db:
        # Get all facilities without program_identifier
        result = await db.execute(
            select(EMDFacility).where(EMDFacility.program_identifier.is_(None))
        )
        facilities = result.scalars().all()
        print(f"Facilities without program_identifier: {len(facilities)}")

        for fac in facilities:
            # Get most recent inspection with a local PDF
            insp_result = await db.execute(
                select(EMDInspection)
                .where(
                    EMDInspection.facility_id == fac.id,
                    EMDInspection.pdf_path.isnot(None),
                    EMDInspection.pdf_path.notlike("/mnt%"),
                )
                .order_by(desc(EMDInspection.inspection_date))
                .limit(1)
            )
            insp = insp_result.scalar_one_or_none()
            if not insp or not insp.pdf_path:
                no_pdf += 1
                continue

            pdf_path = insp.pdf_path
            if not os.path.isabs(pdf_path):
                pdf_path = os.path.join(os.path.dirname(__file__), "..", pdf_path)

            if not os.path.exists(pdf_path):
                no_pdf += 1
                continue

            text = extractor.extract_text(pdf_path)
            prog = extractor._extract_program_identifier(text)
            if prog:
                fac.program_identifier = prog
                updated += 1
            else:
                no_prog += 1

        await db.commit()

    print(f"Updated: {updated} | No PDF: {no_pdf} | No prog identifier in PDF: {no_prog}")


if __name__ == "__main__":
    asyncio.run(main())
