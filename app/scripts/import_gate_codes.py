"""Import gate codes from GateCodes text file.

Run: /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/import_gate_codes.py
"""

import asyncio
import re
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from src.core.database import get_db_context
from src.models.customer import Customer
from src.models.property import Property
from src.models.property_access_code import PropertyAccessCode

GATE_FILE = os.path.expanduser("~/Downloads/GateCodes")

# Label patterns to detect
LABEL_PATTERNS = [
    (r"^(?:Bell\s+)?Gate\s*(?:\d)?:?\s*", "Gate"),
    (r"^Lockbox:?\s*", "Lockbox"),
    (r"^Lock\s+box:?\s*", "Lockbox"),
    (r"^Padlock:?\s*", "Padlock"),
    (r"^Equip(?:ment)?:?\s*", "Equipment"),
    (r"^Combo:?\s*", "Combo"),
    (r"^Chain\s+lock\s*", "Chain Lock"),
    (r"^Gat:?\s*", "Gate"),  # typo in data
]


def parse_gate_file(filepath: str) -> list[dict]:
    """Parse the gate codes file into structured entries."""
    entries = []
    current_name = None
    current_codes = []

    with open(filepath) as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            if current_name and current_codes:
                entries.append({"name": current_name, "codes": current_codes})
            current_name = None
            current_codes = []
            continue

        if current_name is None:
            current_name = line
            continue

        # Parse code line
        label = "Code"
        code = line
        notes = None

        # Check for labeled patterns
        for pattern, lbl in LABEL_PATTERNS:
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                label = lbl
                code = line[m.end():].strip()
                break

        # Handle compound labels like "Bell Gate: #8675" or "Norwood Gate: #2328"
        compound = re.match(r"^(\w+(?:\s+\w+)?)\s+Gate:?\s*(.*)", line, re.IGNORECASE)
        if compound and label == "Code":
            label = f"{compound.group(1).title()} Gate"
            code = compound.group(2).strip()

        # Handle "Arbor 1: 1363" style
        numbered = re.match(r"^(\w+(?:\s+\w+)?)\s+(\d+):?\s*(.*)", line)
        if numbered and label == "Code":
            label = f"{numbered.group(1).title()} {numbered.group(2)}"
            code = numbered.group(3).strip()

        # Extract parenthetical notes
        note_match = re.search(r"\(([^)]+)\)", code)
        if note_match:
            notes = note_match.group(1)
            code = code[:note_match.start()].strip()

        # Clean code
        code = code.strip().lstrip("#")
        if not code:
            continue

        current_codes.append({"label": label, "code": code, "notes": notes})

    # Last entry
    if current_name and current_codes:
        entries.append({"name": current_name, "codes": current_codes})

    return entries


async def import_codes():
    entries = parse_gate_file(GATE_FILE)
    print(f"Parsed {len(entries)} properties from gate codes file")

    async with get_db_context() as db:
        matched = 0
        unmatched = []

        for entry in entries:
            name = entry["name"]

            # Try to match by customer first_name or property address
            prop = None

            # Commercial — match by customer name
            cust_result = await db.execute(
                select(Customer).where(
                    Customer.first_name.ilike(f"%{name}%"),
                    Customer.is_active == True,
                ).limit(1)
            )
            cust = cust_result.scalar_one_or_none()
            if cust:
                prop_result = await db.execute(
                    select(Property).where(
                        Property.customer_id == cust.id,
                        Property.is_active == True,
                    ).limit(1)
                )
                prop = prop_result.scalar_one_or_none()

            # Residential — match by address
            if not prop:
                prop_result = await db.execute(
                    select(Property).where(
                        Property.address.ilike(f"%{name}%"),
                        Property.is_active == True,
                    ).limit(1)
                )
                prop = prop_result.scalar_one_or_none()

            if not prop:
                unmatched.append(f"  {name}: {[c['code'] for c in entry['codes']]}")
                continue

            # Check for existing codes
            existing = (await db.execute(
                select(PropertyAccessCode).where(PropertyAccessCode.property_id == prop.id)
            )).scalars().all()
            existing_codes = {(e.label, e.code) for e in existing}

            added = 0
            for i, code_entry in enumerate(entry["codes"]):
                key = (code_entry["label"], code_entry["code"])
                if key in existing_codes:
                    continue
                ac = PropertyAccessCode(
                    id=str(uuid.uuid4()),
                    property_id=prop.id,
                    label=code_entry["label"],
                    code=code_entry["code"],
                    notes=code_entry["notes"],
                    sort_order=i,
                )
                db.add(ac)
                added += 1

            if added > 0:
                matched += 1
                cust_name = cust.first_name if cust else prop.address
                print(f"  ✓ {name} → {cust_name}: {added} codes added")

        await db.commit()
        print(f"\nMatched: {matched}")
        print(f"Unmatched: {len(unmatched)}")
        if unmatched:
            print("\nUnmatched entries:")
            for u in unmatched:
                print(u)


if __name__ == "__main__":
    asyncio.run(import_codes())
