"""Collapse duplicate-action inbox rules into single any-of rules.

Groups a given org's rules by (field, operator, action signature). If a
group has 2+ rules, their scalar values are merged into an array on a
single surviving rule; the redundant ones are deleted.

Example: 14 rules of the form
    sender_email contains "X" → route_to_spam
collapse to 1 rule
    sender_email contains ["X1", "X2", ... "X14"] → route_to_spam

Rules are ONLY merged when they have:
  - exactly one condition
  - a scalar string value (already-array rules are skipped — they were
    either already collapsed or are user-authored bundles)
  - identical field + operator + normalized-actions signature

Usage:
    python -m scripts.collapse_inbox_rules --dry-run
    python -m scripts.collapse_inbox_rules --org-id <uuid>
    python -m scripts.collapse_inbox_rules --commit   # actually mutate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import delete, select  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.inbox_rule import InboxRule  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("collapse_inbox_rules")


def _action_signature(actions: list[dict]) -> str:
    """Stable string key for an actions list (order-insensitive)."""
    norm = sorted(
        [{"type": a.get("type"), "params": a.get("params") or {}} for a in actions],
        key=lambda a: (a["type"], json.dumps(a["params"], sort_keys=True)),
    )
    return json.dumps(norm, sort_keys=True)


async def collapse(org_id: str | None, commit: bool) -> None:
    async with get_db_context() as db:
        q = select(InboxRule).order_by(InboxRule.priority.asc(), InboxRule.created_at.asc())
        if org_id:
            q = q.where(InboxRule.organization_id == org_id)
        rules = (await db.execute(q)).scalars().all()

        # Group eligible rules by (org_id, field, operator, action_signature)
        groups: dict[tuple, list[InboxRule]] = defaultdict(list)
        skipped = 0
        for r in rules:
            conds = r.conditions or []
            if len(conds) != 1:
                skipped += 1
                continue
            c = conds[0]
            val = c.get("value")
            if not isinstance(val, str):
                skipped += 1
                continue
            key = (
                r.organization_id,
                c.get("field"),
                c.get("operator"),
                _action_signature(r.actions or []),
                bool(r.is_active),
            )
            groups[key].append(r)

        to_merge = {k: g for k, g in groups.items() if len(g) > 1}
        logger.info(
            f"Scanned {len(rules)} rules, {skipped} ineligible, "
            f"found {len(to_merge)} group(s) to merge"
        )

        merged_total = 0
        deleted_total = 0
        for key, members in to_merge.items():
            org, field, operator, _actions_sig, is_active = key
            values = [
                (m.conditions[0]["value"]) for m in members
            ]
            # Keep the highest-priority (lowest number) rule as survivor.
            survivor = min(members, key=lambda m: m.priority)
            deletees = [m for m in members if m.id != survivor.id]

            logger.info(
                f"  Org {org[:8]}: {len(members)} rules → 1 "
                f"(field={field}, op={operator}, active={is_active})"
            )
            logger.info(f"    Values: {values}")
            logger.info(
                f"    Survivor: priority={survivor.priority} id={survivor.id[:8]}"
            )

            if commit:
                survivor.conditions = [
                    {"field": field, "operator": operator, "value": values}
                ]
                survivor.name = None  # force the UI to read the summary
                db.add(survivor)
                await db.execute(
                    delete(InboxRule).where(
                        InboxRule.id.in_([m.id for m in deletees])
                    )
                )
                merged_total += 1
                deleted_total += len(deletees)

        if commit:
            await db.commit()
            logger.info(
                f"COMMITTED. Merged {merged_total} groups, "
                f"deleted {deleted_total} rules"
            )
        else:
            logger.info("(dry-run — no changes written. pass --commit to apply.)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--org-id", help="Limit to one organization")
    p.add_argument("--commit", action="store_true", help="Actually mutate the DB")
    args = p.parse_args()
    asyncio.run(collapse(args.org_id, args.commit))


if __name__ == "__main__":
    main()
