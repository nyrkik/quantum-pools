"""Promise tracker — one-shot backfill of awaiting_reply_until.

For each thread where the most recent INBOUND message contains a
follow-up promise (per orchestrator._is_followup_promise), set
agent_threads.awaiting_reply_until = received_at + 7 days. Skips if a
later inbound exists (the customer has since replied — wait was
already over).

Two-phase: dry-run by default; --apply commits. Last 30 days only,
to avoid surfacing ancient threads.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from src.services.agents.orchestrator import _is_followup_promise


async def main(org_id: str, do_apply: bool):
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://quantumpools:quantumpools@localhost:7062/quantumpools",
    )
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Latest inbound per thread, last 30 days
        rows = (await db.execute(text("""
            WITH latest_inbound AS (
                SELECT DISTINCT ON (m.thread_id)
                    m.thread_id, m.body, m.received_at, m.from_email
                FROM agent_messages m
                JOIN agent_threads t ON t.id = m.thread_id
                WHERE m.organization_id = :org
                  AND m.direction = 'inbound'
                  AND m.received_at >= NOW() - INTERVAL '30 days'
                  AND t.is_historical = false
                  AND t.matched_customer_id IS NOT NULL
                ORDER BY m.thread_id, m.received_at DESC
            )
            SELECT li.thread_id, li.body, li.received_at, li.from_email,
                   t.subject, t.awaiting_reply_until
            FROM latest_inbound li
            JOIN agent_threads t ON t.id = li.thread_id
            WHERE t.awaiting_reply_until IS NULL
        """), {"org": org_id})).all()

        print(f"=== {len(rows)} candidate threads (last 30d, latest inbound only) ===\n")
        to_set = []
        for tid, body, received_at, sender, subject, current_until in rows:
            if _is_followup_promise(body or ""):
                until = received_at + timedelta(days=7)
                to_set.append((tid, until, sender, subject))

        if not to_set:
            print("  No follow-up promises detected.")
            await engine.dispose()
            return

        print(f"  {len(to_set)} threads to set:")
        for tid, until, sender, subject in to_set:
            print(f"    {sender:35} | until={until.date()} | '{(subject or '')[:50]}'")

        if not do_apply:
            print("\nDry run. Re-run with --apply to commit.")
            await engine.dispose()
            return

        print("\nApplying…")
        for tid, until, _, _ in to_set:
            await db.execute(text("""
                UPDATE agent_threads SET awaiting_reply_until = :until
                WHERE id = :tid AND organization_id = :org
            """), {"tid": tid, "until": until, "org": org_id})
        await db.commit()
        print(f"Done. Set awaiting_reply_until on {len(to_set)} threads.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.org_id, args.apply))
