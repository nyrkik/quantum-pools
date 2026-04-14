"""Regenerate classifier drafts for pending inbound messages that are
missing one. Used to heal messages ingested before the raw-MIME unwrap
landed (classifier saw garbage bodies and couldn't draft).

Idempotent — skips anything already drafted, so safe to re-run.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from email import message_from_string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.services.agents.classifier import classify_and_draft  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("regenerate_drafts")


async def run(commit: bool) -> None:
    async with get_db_context() as db:
        targets = (await db.execute(
            select(AgentMessage).where(
                AgentMessage.status == "pending",
                AgentMessage.direction == "inbound",
                (AgentMessage.draft_response.is_(None))
                | (AgentMessage.draft_response == ""),
            )
        )).scalars().all()

        if not targets:
            logger.info("No pending inbound messages are missing drafts.")
            return

        logger.info(f"Regenerating drafts for {len(targets)} message(s)")
        for m in targets:
            try:
                result = await classify_and_draft(
                    m.from_email or "",
                    m.subject or "",
                    m.body or "",
                    from_header=f"{m.from_email}",
                )
                draft = (result or {}).get("draft_response") or ""
                if not draft:
                    logger.info(f"  {m.id[:8]} {m.from_email}: classifier returned no draft")
                    continue

                logger.info(f"  {m.id[:8]} {m.from_email}: {draft[:80]}…")
                if commit:
                    m.draft_response = draft
                    # Only patch category/urgency if the classifier returned them
                    # and the current row is empty — don't re-classify spam to
                    # something else mid-flight.
                    if not m.category and result.get("category"):
                        m.category = result["category"]
                    if not m.urgency and result.get("urgency"):
                        m.urgency = result["urgency"]
                    db.add(m)
            except Exception as e:
                logger.warning(f"  {m.id[:8]} {m.from_email}: classifier failed — {e}")

        if commit:
            await db.commit()
            logger.info("COMMITTED")
        else:
            logger.info("(dry-run — pass --commit to apply)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args.commit))
