"""Merge thread duplicates produced by the FB-57 bug
(corporate `[EXTERNAL]` tags broke thread continuity before the
2026-04-27 normalize_subject fix).

For each cluster of live (non-historical) threads sharing the same
NEW normalized key + contact_email, we:
  1. Pick the oldest thread as primary (the original conversation).
  2. Move all secondary threads' messages + actions onto the primary.
  3. Delete the now-empty secondary threads.
  4. Recompute the primary's message_count + last_direction +
     last_message_at.

Two-phase usage (matches normalize_company_names.py pattern):
  python scripts/merge_duplicate_threads.py --org-id <uuid>
    Dry-run. Prints clusters + the proposed primary for each.
  python scripts/merge_duplicate_threads.py --org-id <uuid> --apply
    Run the merge inside a single transaction. Idempotent on already-
    merged data.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.agent_action import AgentAction
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.utils.thread_utils import normalize_subject


def _new_key(t: AgentThread) -> str:
    return f"{normalize_subject(t.subject or '').lower()}|{(t.contact_email or '').lower()}"


async def find_duplicates(db: AsyncSession, org_id: str):
    rows = (await db.execute(
        select(AgentThread).where(
            AgentThread.organization_id == org_id,
            AgentThread.is_historical.is_(False),
        )
    )).scalars().all()
    groups: dict[str, list[AgentThread]] = {}
    for t in rows:
        groups.setdefault(_new_key(t), []).append(t)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    # Sort each cluster: primary is OLDEST.
    for v in dupes.values():
        v.sort(key=lambda t: t.created_at)
    return dupes


async def merge_cluster(db: AsyncSession, primary: AgentThread, secondaries: list[AgentThread]) -> tuple[int, int]:
    """Repoint messages + actions onto primary; delete secondaries.
    Returns (msgs_moved, actions_moved)."""
    secondary_ids = [t.id for t in secondaries]

    msg_result = await db.execute(
        update(AgentMessage)
        .where(AgentMessage.thread_id.in_(secondary_ids))
        .values(thread_id=primary.id)
    )
    actions_result = await db.execute(
        update(AgentAction)
        .where(AgentAction.thread_id.in_(secondary_ids))
        .values(thread_id=primary.id)
    )
    await db.execute(
        delete(AgentThread).where(AgentThread.id.in_(secondary_ids))
    )
    return msg_result.rowcount or 0, actions_result.rowcount or 0


async def recompute_thread_state(db: AsyncSession, thread: AgentThread) -> None:
    """After merging, derive message_count + last_direction +
    last_message_at + status from the new message set."""
    msgs = (await db.execute(
        select(AgentMessage)
        .where(AgentMessage.thread_id == thread.id)
        .order_by(AgentMessage.received_at.desc())
    )).scalars().all()

    thread.message_count = len(msgs)
    if msgs:
        most_recent = msgs[0]
        thread.last_direction = most_recent.direction
        thread.last_message_at = most_recent.received_at
        # If the latest message is inbound and at least one message is
        # pending → thread.status=pending. Otherwise leave as-is.
        any_pending = any(m.status == "pending" for m in msgs)
        if any_pending and most_recent.direction == "inbound":
            thread.status = "pending"
    await db.flush()


async def run(org_id: str, do_apply: bool):
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://quantumpools:quantumpools@localhost:7062/quantumpools",
    )
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        dupes = await find_duplicates(db, org_id)
        if not dupes:
            print(f"✓ No live duplicate threads for org {org_id}.")
            await engine.dispose()
            return

        print(f"=== {len(dupes)} duplicate clusters ===\n")
        for new_key, threads in dupes.items():
            primary = threads[0]
            secondaries = threads[1:]
            print(f"  cluster: {new_key!r}")
            print(f"    primary  {primary.id[:8]}  msgs={primary.message_count}  created={primary.created_at}")
            for s in secondaries:
                print(f"    merge ←  {s.id[:8]}  msgs={s.message_count}  created={s.created_at}")
            print()

        if not do_apply:
            print("Dry run — re-run with --apply to merge.")
            await engine.dispose()
            return

        print("Applying merges…\n")
        total_msgs = 0
        total_actions = 0
        for threads in dupes.values():
            primary = threads[0]
            secondaries = threads[1:]
            msgs_moved, actions_moved = await merge_cluster(db, primary, secondaries)
            total_msgs += msgs_moved
            total_actions += actions_moved
            await recompute_thread_state(db, primary)
            print(f"  ✓ {primary.subject!r}: moved {msgs_moved} msgs, {actions_moved} actions; deleted {len(secondaries)} secondaries")
        await db.commit()
        print(f"\nDone. {total_msgs} messages + {total_actions} actions repointed.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--apply", action="store_true",
                        help="Actually run the merge (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(run(args.org_id, args.apply))
