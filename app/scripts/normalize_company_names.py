"""Standardize Customer.company_name spellings within an org.

Two-phase usage:

  python scripts/normalize_company_names.py --org-id <uuid>
    Dry-run. Prints clusters + the proposed canonical for each.
    Output is a JSON file at /tmp/qp-name-normalize-<org>.json that
    you can hand-edit to override any canonical pick.

  python scripts/normalize_company_names.py --org-id <uuid> --apply
    Reads the JSON file produced by dry-run (must exist), confirms,
    runs the renames in a single transaction, and prints a summary.
    Idempotent on already-canonicalized data.

Why dry-run-then-apply: mode-wins canonical picking is a heuristic
(e.g., 'BLVD' wins over 'BLVD Residential' just on count). For a
B2B database this is real customer data — having a human review
the canonicals before persisting is worth the extra step.

The frontend's company-name typeahead handles the *future* additions
side; this script handles the existing-data backfill.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.customer import Customer
from src.services.customers.normalizer import CompanyNameNormalizer


def _output_path(org_id: str) -> str:
    return f"/tmp/qp-name-normalize-{org_id}.json"


async def dry_run(org_id: str, db: AsyncSession) -> int:
    norm = CompanyNameNormalizer(db)
    clusters = await norm.cluster_existing(org_id)

    if not clusters:
        print(f"✓ No spelling clusters found for org {org_id}.")
        print("  Either the data is already standardized or there are too few customers.")
        return 0

    plan = []
    print(f"=== {len(clusters)} clusters found ===\n")
    for c in clusters:
        print(f"  Canonical proposed: {c.canonical!r}")
        for member in c.members:
            count = c.counts.get(member, 0)
            marker = "  ← canonical" if member == c.canonical else ""
            print(f"    {count:3}× {member!r}{marker}")
        print(f"    total rows affected: {c.total_rows}")
        print()
        plan.append({
            "canonical": c.canonical,
            "members": c.members,
            "counts": c.counts,
            "total_rows": c.total_rows,
        })

    out = _output_path(org_id)
    with open(out, "w") as f:
        json.dump({"org_id": org_id, "clusters": plan}, f, indent=2)
    print(f"Wrote plan to {out}")
    print()
    print("To apply: edit the JSON if you want to override any canonical, then re-run with --apply.")
    return len(clusters)


async def apply(org_id: str, db: AsyncSession) -> int:
    out = _output_path(org_id)
    if not os.path.exists(out):
        print(f"ERR: no plan found at {out}. Run --dry-run first.")
        return 1
    with open(out) as f:
        plan = json.load(f)
    if plan.get("org_id") != org_id:
        print(f"ERR: plan org mismatch ({plan.get('org_id')} != {org_id})")
        return 1

    total_changed = 0
    for cluster in plan["clusters"]:
        canonical = cluster["canonical"]
        members = cluster["members"]
        # Update only members that aren't already canonical.
        targets = [m for m in members if m != canonical]
        if not targets:
            continue
        result = await db.execute(
            update(Customer)
            .where(
                Customer.organization_id == org_id,
                Customer.company_name.in_(targets),
            )
            .values(company_name=canonical)
        )
        rowcount = result.rowcount or 0
        total_changed += rowcount
        print(f"  ✓ {canonical!r}: renamed {rowcount} rows from {targets}")

    await db.commit()
    print(f"\nDone. Total Customer rows updated: {total_changed}")
    return 0


async def main(org_id: str, do_apply: bool):
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://quantumpools:quantumpools@localhost:7062/quantumpools",
    )
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        if do_apply:
            await apply(org_id, db)
        else:
            await dry_run(org_id, db)
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply the plan from /tmp/qp-name-normalize-<org>.json. "
             "Default is dry-run.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.org_id, args.apply))
