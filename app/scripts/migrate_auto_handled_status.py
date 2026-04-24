"""Backfill: reclassify legacy `agent_threads.status='ignored'` rows that
were really AI auto-closes.

Pre-2026-04-25 derivation of `update_thread_status` set the thread to
`status='ignored'` when an inbound was AI-auto-closed (msg.status='handled')
but no outbound was ever sent. The default Inbox query then filtered
ignored — making legitimate informational mail (Workspace notifications,
billing receipts) invisible to users.

The new derivation produces `status='handled'` + `auto_handled_at` for the
same shape, surfacing those threads in the AI Review folder and the
Handled segment. This script ports the existing data into the new model.

Heuristic:
  - thread.status='ignored' (the symptom)
  - is_historical=False
  - has at least one inbound message with status='handled' (AI's signal)
  - has NO outbound message in ('sent','auto_sent') (not a human reply)

Sets status='handled', auto_handled_at = MIN(received_at) of the matching
inbound. `auto_handled_feedback_at` is left NULL so backfilled threads
appear in the AI Review folder for a one-time admin catch-up pass.

User-archived threads (manual dismiss) keep status='ignored' — they don't
match the heuristic since no inbound message has status='handled' for
those.

Run from /srv/quantumpools/app:

    /home/brian/00_MyProjects/QuantumPools/venv/bin/python \\
        scripts/migrate_auto_handled_status.py --dry-run

    /home/brian/00_MyProjects/QuantumPools/venv/bin/python \\
        scripts/migrate_auto_handled_status.py

Idempotent — re-running after a successful pass is a no-op (rows already
flipped to status='handled' won't match the predicate).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from src.core.database import get_db_context  # noqa: E402


CANDIDATE_SQL = text(
    """
    SELECT
      t.id,
      t.contact_email,
      t.subject,
      t.last_message_at,
      (
        SELECT MIN(m.received_at) FROM agent_messages m
        WHERE m.thread_id = t.id
          AND m.direction = 'inbound'
          AND m.status = 'handled'
      ) AS earliest_handled_inbound_at
    FROM agent_threads t
    WHERE t.status = 'ignored'
      AND t.is_historical = FALSE
      AND EXISTS (
        SELECT 1 FROM agent_messages m
        WHERE m.thread_id = t.id
          AND m.direction = 'inbound'
          AND m.status = 'handled'
      )
      AND NOT EXISTS (
        SELECT 1 FROM agent_messages m
        WHERE m.thread_id = t.id
          AND m.direction = 'outbound'
          AND m.status IN ('sent', 'auto_sent')
      )
    ORDER BY t.last_message_at DESC
    """
)

UPDATE_SQL = text(
    """
    UPDATE agent_threads t
    SET status = 'handled',
        auto_handled_at = (
          SELECT MIN(m.received_at) FROM agent_messages m
          WHERE m.thread_id = t.id
            AND m.direction = 'inbound'
            AND m.status = 'handled'
        )
    WHERE t.status = 'ignored'
      AND t.is_historical = FALSE
      AND EXISTS (
        SELECT 1 FROM agent_messages m
        WHERE m.thread_id = t.id
          AND m.direction = 'inbound'
          AND m.status = 'handled'
      )
      AND NOT EXISTS (
        SELECT 1 FROM agent_messages m
        WHERE m.thread_id = t.id
          AND m.direction = 'outbound'
          AND m.status IN ('sent', 'auto_sent')
      )
    """
)


async def run(dry_run: bool, sample_size: int) -> int:
    async with get_db_context() as db:
        rows = (await db.execute(CANDIDATE_SQL)).all()
        total = len(rows)

        print(f"Candidates: {total} thread(s) match the AI-auto-close heuristic.")
        if total == 0:
            return 0

        print(f"Sample (first {min(sample_size, total)}):")
        for r in rows[:sample_size]:
            subj = (r.subject or "").strip()[:60]
            print(
                f"  thread={r.id[:8]} from={r.contact_email[:40]:<40} "
                f"last_msg={r.last_message_at} earliest_handled={r.earliest_handled_inbound_at} "
                f"subj={subj!r}"
            )

        if dry_run:
            print("\n--dry-run: no changes written.")
            return total

        result = await db.execute(UPDATE_SQL)
        await db.commit()
        rowcount = result.rowcount or 0
        print(f"\nUpdated {rowcount} thread(s).")
        return rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print counts + sample, no writes.")
    parser.add_argument("--sample", type=int, default=10, help="Sample rows to print (default 10).")
    args = parser.parse_args()

    asyncio.run(run(args.dry_run, args.sample))


if __name__ == "__main__":
    main()
