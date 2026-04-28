"""One-shot backfill: auto-handle existing pending threads from
TRANSACTIONAL_NOTIFICATION_SENDERS.

The orchestrator gained a transactional-sender shortcut on 2026-04-27 that
forces no_response for known FYI-only senders (Stripe payouts, Amex transfer
confirmations, AppFolio digests). Threads already in the inbox before that
shortcut existed sit pending; this backfill reclassifies them: thread.status
= handled, has_pending = False, message status = handled, category preserved
so they stay in the right folder.

Two-phase: dry-run by default; --apply commits.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


# Mirror of the orchestrator constant — keep in sync with
# src/services/agents/orchestrator.py:TRANSACTIONAL_NOTIFICATION_SENDERS.
TRANSACTIONAL_NOTIFICATION_SENDERS = (
    "notifications@stripe.com",
    "@welcome.americanexpress.com",
    "donotreply@appfolio.com",
)


async def main(org_id: str, do_apply: bool):
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://quantumpools:quantumpools@localhost:7062/quantumpools",
    )
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Build sender LIKE pattern list
        like_clauses = " OR ".join([f"LOWER(t.contact_email) LIKE :pat{i}"
                                     for i in range(len(TRANSACTIONAL_NOTIFICATION_SENDERS))])
        params = {"org": org_id}
        for i, p in enumerate(TRANSACTIONAL_NOTIFICATION_SENDERS):
            params[f"pat{i}"] = f"%{p.lower()}%"

        rows = (await db.execute(text(f"""
            SELECT t.id, t.subject, t.contact_email, t.status, t.has_pending
            FROM agent_threads t
            WHERE t.organization_id = :org
              AND t.is_historical = false
              AND t.has_pending = true
              AND ({like_clauses})
            ORDER BY t.last_message_at DESC
        """), params)).all()

        print(f"=== {len(rows)} pending threads from transactional senders ===\n")
        for r in rows:
            print(f"  {r.id[:8]} | {r.contact_email:50} | {(r.subject or '(none)')[:55]}")

        if not rows:
            print("\n  Nothing to backfill.")
            await engine.dispose()
            return

        if not do_apply:
            print("\nDry run. Re-run with --apply to commit.")
            await engine.dispose()
            return

        print("\nApplying…")
        for r in rows:
            await db.execute(text("""
                UPDATE agent_threads
                SET status = 'handled',
                    has_pending = false,
                    auto_handled_at = COALESCE(auto_handled_at, NOW())
                WHERE id = :tid AND organization_id = :org
            """), {"tid": r.id, "org": org_id})
            await db.execute(text("""
                UPDATE agent_messages
                SET status = 'handled', category = 'no_response'
                WHERE thread_id = :tid AND direction = 'inbound' AND status = 'pending'
            """), {"tid": r.id})
        await db.commit()
        print(f"Done. Auto-handled {len(rows)} threads.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.org_id, args.apply))
