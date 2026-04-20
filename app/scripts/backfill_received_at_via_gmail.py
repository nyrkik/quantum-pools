"""Backfill: recover real ``received_at`` for legacy rows via Gmail API.

The old IMAP-based ingest stamped ``AgentMessage.received_at`` with
INGEST time instead of parsing the email's ``Date:`` header. Result:
141 rows in Sapphire (integer ``email_uid`` like ``715``, ``1361``)
show the date we pulled the message, not the date it was sent.

Example that surfaced this — Bill Hoge's Google Voice SMS
notification: actually left 2025-06-19, stored as 2026-03-23.

The current orchestrator honors the Date header correctly
(``parsedate_to_datetime(msg.get('Date'))``). This script fixes the
historical rows by searching Gmail per-message and taking Gmail's
``internalDate`` — authoritative server-side timestamp, in ms since
epoch, unaffected by ingest delays.

Usage:
    ./venv/bin/python app/scripts/backfill_received_at_via_gmail.py --dry-run
    ./venv/bin/python app/scripts/backfill_received_at_via_gmail.py

Idempotent — skips rows whose current received_at already matches
Gmail's internalDate within 60s. Rate-limited by Gmail API quota
(~250 req/sec default; this runs ~2 calls per row so well under).
Hits rows that can't be uniquely matched in Gmail are logged and
left untouched.

After updating messages, recomputes ``agent_threads.last_message_at``
and ``last_direction`` from the corrected message timestamps, so
the inbox sort order reflects reality.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
)

from sqlalchemy import desc, func, select, update  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.models.agent_thread import AgentThread  # noqa: E402
from src.models.email_integration import EmailIntegration  # noqa: E402
from src.services.gmail.client import build_gmail_client  # noqa: E402


# Rows with integer email_uids (e.g., "715", "1361") are the legacy
# IMAP ingest. Current ingest uses "gm-..." (Gmail API) or "pm-..."
# (Postmark webhook) prefixes.
LEGACY_UID_CLAUSE = "email_uid ~ '^[0-9]+$'"


def _escape_gmail_query(value: str) -> str:
    """Gmail query escaping: double quotes for exact match, backslash
    escape internal double quotes. Newlines stripped — subjects with
    embedded newlines shouldn't hit the search."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def _gmail_lookup_internal_date(
    client, from_email: str, subject: str, approx_time: datetime,
) -> Optional[datetime]:
    """Search Gmail for one message matching ``from:<sender>`` and the
    subject, return its ``internalDate`` as a tz-aware UTC datetime.

    Uses a ±365-day window anchored on the provided ``approx_time`` to
    narrow the search (legacy received_at could be months off, but not
    years). When multiple hits come back, picks the one closest to
    ``approx_time`` — the right choice when a single sender sent
    repeated identical subjects (e.g., "New text message from (555)…").
    """
    if not from_email or not subject:
        return None

    q = (
        f'from:"{_escape_gmail_query(from_email)}" '
        f'subject:"{_escape_gmail_query(subject)}" '
        f'after:{(approx_time - timedelta(days=365)).strftime("%Y/%m/%d")} '
        f'before:{(approx_time + timedelta(days=2)).strftime("%Y/%m/%d")}'
    )
    try:
        resp = client.users().messages().list(
            userId="me", q=q, maxResults=5,
        ).execute()
    except Exception as e:  # noqa: BLE001
        print(f"  gmail list failed: {e}")
        return None

    msgs = resp.get("messages", [])
    if not msgs:
        return None

    best: Optional[tuple[int, datetime]] = None
    for m in msgs:
        try:
            meta = client.users().messages().get(
                userId="me", id=m["id"], format="minimal",
            ).execute()
        except Exception as e:  # noqa: BLE001
            print(f"  gmail get failed for {m['id']}: {e}")
            continue
        raw_ms = meta.get("internalDate")
        if not raw_ms:
            continue
        dt = datetime.fromtimestamp(int(raw_ms) / 1000.0, tz=timezone.utc)
        delta = abs((dt - approx_time).total_seconds())
        if best is None or delta < best[0]:
            best = (delta, dt)
    return best[1] if best else None


async def _recompute_thread_denorms(db, thread_ids: set[str]) -> None:
    """After updating message timestamps, fix up the thread-level
    denorms so the inbox sort + 'last direction' denormalization
    reflect the new (correct) timestamps."""
    if not thread_ids:
        return
    for tid in thread_ids:
        row = (await db.execute(
            select(
                func.max(AgentMessage.received_at),
            ).where(AgentMessage.thread_id == tid)
        )).first()
        max_received = row[0] if row else None
        if max_received is None:
            continue

        latest_dir = (await db.execute(
            select(AgentMessage.direction)
            .where(AgentMessage.thread_id == tid)
            .order_by(desc(AgentMessage.received_at))
            .limit(1)
        )).scalar_one_or_none()

        await db.execute(
            update(AgentThread)
            .where(AgentThread.id == tid)
            .values(
                last_message_at=max_received,
                last_direction=latest_dir or "inbound",
            )
        )


async def main(dry_run: bool = False, max_rows: int | None = None) -> None:
    async with get_db_context() as db:
        # Candidate messages — integer uids, with subject + from_email.
        # Skip rows where we can't search (no subject / no sender).
        rows = (await db.execute(
            select(
                AgentMessage.id, AgentMessage.organization_id,
                AgentMessage.thread_id, AgentMessage.email_uid,
                AgentMessage.from_email, AgentMessage.subject,
                AgentMessage.received_at,
            )
            .where(
                AgentMessage.email_uid.op("~")(r"^[0-9]+$"),
                AgentMessage.from_email.is_not(None),
                AgentMessage.subject.is_not(None),
            )
            .order_by(AgentMessage.received_at)
        )).all()

        if max_rows is not None:
            rows = rows[:max_rows]

        print(f"Candidate rows: {len(rows)}")

        # Cache gmail clients per org.
        clients: dict[str, object] = {}

        matched = 0
        updated = 0
        skipped_no_integration = 0
        skipped_no_match = 0
        skipped_unchanged = 0
        touched_threads: set[str] = set()

        for row in rows:
            mid = row.id
            org_id = row.organization_id
            tid = row.thread_id
            from_email = row.from_email or ""
            subject = row.subject or ""
            approx = row.received_at

            client = clients.get(org_id)
            if client is None and org_id not in clients:
                integ = (await db.execute(
                    select(EmailIntegration).where(
                        EmailIntegration.organization_id == org_id,
                        EmailIntegration.type == "gmail_api",
                        EmailIntegration.status == "connected",
                    )
                )).scalar_one_or_none()
                if integ is None:
                    clients[org_id] = None
                else:
                    try:
                        clients[org_id] = build_gmail_client(integ)
                    except Exception as e:  # noqa: BLE001
                        print(f"  gmail client build failed for {org_id}: {e}")
                        clients[org_id] = None
                client = clients[org_id]
            if client is None:
                skipped_no_integration += 1
                continue

            real_dt = _gmail_lookup_internal_date(
                client, from_email, subject, approx,
            )
            if real_dt is None:
                skipped_no_match += 1
                continue

            # Idempotency — already within a minute, skip.
            if abs((real_dt - approx).total_seconds()) < 60:
                skipped_unchanged += 1
                continue

            matched += 1
            print(
                f"  {mid[:8]}… {from_email[:40]:40s} "
                f"{approx.strftime('%Y-%m-%d')} → {real_dt.strftime('%Y-%m-%d')}"
                f"   [{subject[:60]}]"
            )
            if not dry_run:
                await db.execute(
                    update(AgentMessage)
                    .where(AgentMessage.id == mid)
                    .values(received_at=real_dt)
                )
                updated += 1
                if tid:
                    touched_threads.add(tid)

        if not dry_run:
            await _recompute_thread_denorms(db, touched_threads)
            await db.commit()
            print(
                f"\nCommitted {updated} received_at updates "
                f"+ {len(touched_threads)} thread denorm refreshes."
            )
        else:
            print(f"\nDRY RUN — {matched} rows would be updated.")
            await db.rollback()

        print(
            f"Stats: matched={matched} skipped_no_integration="
            f"{skipped_no_integration} skipped_no_match={skipped_no_match} "
            f"skipped_unchanged={skipped_unchanged}"
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Don't commit; show what would change.")
    p.add_argument("--max-rows", type=int, default=None,
                   help="Cap rows processed this run (useful for testing).")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run, max_rows=args.max_rows))
