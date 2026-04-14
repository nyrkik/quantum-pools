"""One-shot backfill: unwrap any agent_messages whose body is still the
raw MIME multipart envelope delivered by Postmark for Outlook/Exchange
senders before commit f48a91f was deployed.

Safe to re-run — skips anything that doesn't look like a raw MIME envelope
(the unwrap function is a no-op in that case).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.services.agents.mail_agent import _unwrap_embedded_mime  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("unwrap_stored_mime")


async def run(commit: bool) -> None:
    async with get_db_context() as db:
        rows = (await db.execute(
            select(AgentMessage).where(
                AgentMessage.body.like("--%"),
                AgentMessage.body.like("%Content-Type:%"),
            )
        )).scalars().all()

        changed = 0
        for m in rows:
            unwrapped = _unwrap_embedded_mime(m.body or "")
            if unwrapped == m.body:
                continue
            preview = unwrapped.splitlines()[0][:80] if unwrapped else ""
            logger.info(f"  {m.id[:8]} {m.from_email}: {preview}")
            if commit:
                m.body = unwrapped
                db.add(m)
            changed += 1

        if commit:
            await db.commit()
            logger.info(f"COMMITTED. Unwrapped {changed} messages.")
        else:
            logger.info(f"(dry-run) Would unwrap {changed} messages.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args.commit))
