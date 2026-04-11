"""Backfill: re-clean agent_messages.body rows where Postmark leaked a raw
multipart MIME envelope into TextBody.

Run from project root:
    /home/brian/00_MyProjects/QuantumPools/venv/bin/python app/scripts/backfill_unwrap_mime_bodies.py
"""

import asyncio
import sys
from pathlib import Path

# Make `src.*` importable when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.agent_message import AgentMessage
from src.services.agents.mail_agent import _unwrap_embedded_mime


async def main(dry_run: bool = False):
    async with get_db_context() as db:
        # Same regex as the diagnosis query — leading boundary then Content-Type header
        result = await db.execute(
            select(AgentMessage).where(
                AgentMessage.body.op("~")(r"^--[A-Za-z0-9_]+\s*\nContent-Type:")
            )
        )
        rows = result.scalars().all()

        print(f"Found {len(rows)} affected messages")
        changed = 0

        for msg in rows:
            original = msg.body or ""
            cleaned = _unwrap_embedded_mime(original)
            if cleaned == original:
                print(f"  - {msg.id}: helper made no change, skipping")
                continue
            print(
                f"  - {msg.id}: {len(original)} -> {len(cleaned)} chars"
                f" | preview: {cleaned[:80]!r}"
            )
            if not dry_run:
                msg.body = cleaned[:5000]
                changed += 1

        if dry_run:
            print(f"DRY RUN — would update {len([r for r in rows if _unwrap_embedded_mime(r.body or '') != (r.body or '')])} rows")
            await db.rollback()
        else:
            await db.commit()
            print(f"Committed {changed} updates")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry))
