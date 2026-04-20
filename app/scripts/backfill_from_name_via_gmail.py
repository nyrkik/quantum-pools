"""Backfill: recover ``agent_messages.from_name`` from Gmail API.

The ``from_name`` column was added after the ingest had been running
for a while, so every existing row started with NULL. For rows whose
thread has a ``gmail_thread_id``, we can re-fetch the Gmail thread,
walk its messages, and extract the From header's display name via
the same ``parse_from_header`` helper the live ingest uses.

Coverage (verified on Sapphire 2026-04-20):
    500 total messages with from_name NULL
    ├── 255 recoverable via Gmail API (thread has gmail_thread_id)
    └── 245 not recoverable (Postmark inbound + legacy rows) —
        original From header isn't stored anywhere retrievable.

Run from project root:

    ./venv/bin/python app/scripts/backfill_from_name_via_gmail.py --dry-run
    ./venv/bin/python app/scripts/backfill_from_name_via_gmail.py

Idempotent — already-populated rows are skipped. Safe to re-run.
Rate-limited to the Gmail integration's quota (250 req/sec default);
we fetch one thread at a time with format=metadata so each call is
cheap. No retries on transient errors — re-run to pick up failures.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
)

from sqlalchemy import select, update  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.models.agent_thread import AgentThread  # noqa: E402
from src.models.email_integration import EmailIntegration  # noqa: E402
from src.services.agents.mail_agent import parse_from_header  # noqa: E402
from src.services.gmail.client import build_gmail_client  # noqa: E402


def _uid_from_gmail_id(gmail_message_id: str) -> str:
    """Mirror ``gmail/sync.py``'s uid derivation so we can match by
    email_uid without storing gmail_message_id separately."""
    return f"gm-{hashlib.sha256(gmail_message_id.encode()).hexdigest()[:32]}"


def _from_header_from_headers(headers: list[dict]) -> str:
    for h in headers or []:
        if h.get("name", "").lower() == "from":
            return h.get("value", "")
    return ""


async def _load_candidates(db) -> dict[str, dict]:
    """Group candidate AgentMessage rows by ``(integration_id,
    gmail_thread_id)``. Each entry is a dict keyed by email_uid so
    we can match headers back to rows after the API call."""
    rows = (await db.execute(
        select(
            AgentMessage.id,
            AgentMessage.email_uid,
            AgentMessage.organization_id,
            AgentThread.gmail_thread_id,
        )
        .join(AgentThread, AgentThread.id == AgentMessage.thread_id)
        .where(
            AgentMessage.from_name.is_(None),
            AgentThread.gmail_thread_id.is_not(None),
            AgentMessage.email_uid.like("gm-%"),
        )
    )).all()

    grouped: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for msg_id, email_uid, org_id, gmail_thread_id in rows:
        grouped[(org_id, gmail_thread_id)][email_uid] = msg_id
    return grouped


async def _load_integration_by_org(db, org_id: str) -> Optional[EmailIntegration]:
    row = (await db.execute(
        select(EmailIntegration).where(
            EmailIntegration.organization_id == org_id,
            EmailIntegration.type == "gmail_api",
            EmailIntegration.status == "connected",
        )
    )).scalar_one_or_none()
    return row


def _extract_from_names(
    client, gmail_thread_id: str,
) -> dict[str, str]:
    """Call users.threads.get on a Gmail thread, walk its messages,
    parse the From header, return ``{email_uid: from_name}`` for
    messages whose From header carried a display name."""
    try:
        thread = client.users().threads().get(
            userId="me",
            id=gmail_thread_id,
            format="metadata",
            metadataHeaders=["From"],
        ).execute()
    except Exception as e:  # noqa: BLE001
        print(f"  gmail thread fetch failed for {gmail_thread_id}: {e}")
        return {}

    out: dict[str, str] = {}
    for msg in thread.get("messages", []):
        gmail_msg_id = msg.get("id")
        if not gmail_msg_id:
            continue
        uid = _uid_from_gmail_id(gmail_msg_id)
        headers = (msg.get("payload") or {}).get("headers") or []
        raw_from = _from_header_from_headers(headers)
        if not raw_from:
            continue
        from_name, _ = parse_from_header(raw_from)
        if from_name and from_name.strip() and "@" not in from_name:
            out[uid] = from_name.strip()[:200]
    return out


async def main(dry_run: bool = False, max_threads: int | None = None) -> None:
    async with get_db_context() as db:
        grouped = await _load_candidates(db)
        total_threads = len(grouped)
        total_rows = sum(len(v) for v in grouped.values())
        print(f"Candidate: {total_rows} messages across {total_threads} Gmail threads")

        if max_threads is not None:
            limited = {}
            for i, (k, v) in enumerate(grouped.items()):
                if i >= max_threads:
                    break
                limited[k] = v
            grouped = limited
            print(f"Limited to {len(grouped)} threads for this run")

        # Cache integrations so we don't refetch per-org.
        integrations: dict[str, EmailIntegration] = {}
        clients: dict[str, object] = {}

        matched = 0
        skipped_no_integration = 0

        for (org_id, gmail_thread_id), row_map in grouped.items():
            integ = integrations.get(org_id)
            if integ is None and org_id not in integrations:
                integ = await _load_integration_by_org(db, org_id)
                integrations[org_id] = integ
            if integ is None:
                skipped_no_integration += len(row_map)
                continue

            client = clients.get(org_id)
            if client is None:
                try:
                    client = build_gmail_client(integ)
                    clients[org_id] = client
                except Exception as e:  # noqa: BLE001
                    print(f"  gmail client build failed for org {org_id}: {e}")
                    continue

            uid_to_name = _extract_from_names(client, gmail_thread_id)
            for uid, from_name in uid_to_name.items():
                if uid not in row_map:
                    continue
                matched += 1
                print(
                    f"  {uid} → {from_name!r}"
                    f"  (msg id: {row_map[uid]})"
                )
                if not dry_run:
                    await db.execute(
                        update(AgentMessage)
                        .where(AgentMessage.email_uid == uid)
                        .values(from_name=from_name)
                    )

        if dry_run:
            print(f"DRY RUN — would populate from_name for {matched} messages")
            await db.rollback()
        else:
            await db.commit()
            print(f"Committed {matched} from_name updates")

        if skipped_no_integration:
            print(
                f"Skipped {skipped_no_integration} messages whose org has no "
                f"connected gmail_api integration — these stay NULL.",
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Don't commit; just print what would change.")
    p.add_argument("--max-threads", type=int, default=None,
                   help="Cap number of Gmail threads fetched (useful for testing).")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run, max_threads=args.max_threads))
