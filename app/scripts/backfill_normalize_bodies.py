"""Backfill: re-normalize agent_messages.{body, body_html} for rows where
quoted-printable escapes or raw HTML leaked into the plain-text body.

Companion to `backfill_unwrap_mime_bodies.py`, which handled the
`--boundary ... Content-Type:` quirk. This script handles the two
other TextBody quirks that `_normalize_body` now fixes at ingest
time:

  1. Raw `=3D` / `=09` / `=\\n` (quoted-printable) escapes — common
     in Yardi/ACH/property-management emails relayed via Postmark
     where the upstream Content-Transfer-Encoding header is missing.
  2. Raw HTML in TextBody with no HtmlBody — the body looks like a
     wall of tags in inbox rows.

Run from project root:

    ./venv/bin/python app/scripts/backfill_normalize_bodies.py --dry-run
    ./venv/bin/python app/scripts/backfill_normalize_bodies.py

Idempotent — rows already cleaned will produce no change and be
skipped. Safe to re-run.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import or_, select  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.models.agent_thread import AgentThread  # noqa: E402
from src.services.agents.mail_agent import (  # noqa: E402
    _normalize_body,
    _looks_like_html,
    _looks_quoted_printable,
    strip_email_signature,
    strip_quoted_reply,
)


def _needs_normalize(body: str | None, body_html: str | None) -> bool:
    """Only touch rows where `_normalize_body` would actually change
    something. Keeps the dry-run count honest and avoids no-op writes."""
    if not body:
        return False
    return _looks_quoted_printable(body) or _looks_like_html(body)


def _recompute_snippet(body: str) -> str:
    """Mirror thread_manager.update_status_from_messages — snippet is the
    first 200 chars of the quoted-reply + signature-stripped body."""
    clean = strip_email_signature(strip_quoted_reply(body or ""))
    return clean[:200]


async def _refresh_thread_snippets(db, dry_run: bool) -> int:
    """Recompute `agent_threads.last_snippet` for any thread whose current
    snippet still carries QP tokens or HTML tags. Runs after the message
    bodies have been normalized, so the snippet picks up the cleaned text.

    Scoped to threads where the SNIPPET itself looks bad (not the body) —
    a cheap, targeted sweep that doesn't force-refresh every thread in
    the org.
    """
    candidates = (await db.execute(
        select(AgentThread).where(
            or_(
                AgentThread.last_snippet.like("%=3D%"),
                AgentThread.last_snippet.like("%=09%"),
                AgentThread.last_snippet.op("~*")(
                    r"<(html|body|div|table|tbody|tr|td|style|head|p|span)\b"
                ),
            )
        )
    )).scalars().all()

    updated = 0
    for t in candidates:
        # Pull the latest message's body — match thread_manager's ordering.
        last_body = (await db.execute(
            select(AgentMessage.body)
            .where(AgentMessage.thread_id == t.id)
            .order_by(AgentMessage.received_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if last_body is None:
            continue
        new_snip = _recompute_snippet(last_body)
        if new_snip == (t.last_snippet or ""):
            continue
        print(
            f"  thread {t.id}: snippet {len(t.last_snippet or '')}→"
            f"{len(new_snip)} chars | preview {new_snip[:60]!r}"
        )
        updated += 1
        if not dry_run:
            t.last_snippet = new_snip
    return updated


async def main(dry_run: bool = False) -> None:
    async with get_db_context() as db:
        # Candidate query — anything that contains a QP token OR an HTML
        # structural tag in `body`. This is a superset of rows
        # `_normalize_body` will actually rewrite (the Python check is
        # authoritative).
        result = await db.execute(
            select(AgentMessage).where(
                or_(
                    AgentMessage.body.like("%=3D%"),
                    AgentMessage.body.like("%=09%"),
                    AgentMessage.body.like("%=%\n%"),
                    AgentMessage.body.op("~*")(
                        r"<(html|body|div|table|tbody|tr|td|style|head|p|span)\b"
                    ),
                )
            )
        )
        rows = result.scalars().all()

        print(f"Candidate rows: {len(rows)}")
        would_change = 0
        changed = 0

        for msg in rows:
            original = msg.body or ""
            if not _needs_normalize(original, msg.body_html):
                continue
            new_body, new_html, _diag = _normalize_body(original, msg.body_html)
            if new_body == original and (new_html or None) == (msg.body_html or None):
                continue

            would_change += 1
            print(
                f"  - {msg.id} ({msg.from_email}): "
                f"body {len(original)}→{len(new_body)} "
                f"| preview {new_body[:60]!r}"
            )
            if not dry_run:
                # AgentMessage.body is TEXT — no length cap in the model,
                # but prior backfill capped at 5000 for sanity. Keep that
                # here so backfilled rows match the shape of freshly
                # ingested ones.
                msg.body = new_body[:5000]
                if new_html and not msg.body_html:
                    msg.body_html = new_html
                changed += 1

        # Snippet refresh pass — thread-level denorm of the cleaned body.
        print()
        print("Refreshing agent_threads.last_snippet for stale snippets…")
        snippet_updates = await _refresh_thread_snippets(db, dry_run)

        if dry_run:
            print(f"DRY RUN — would update {would_change} message row(s) + {snippet_updates} thread snippet(s)")
            await db.rollback()
        else:
            await db.commit()
            print(f"Committed {changed} message update(s) + {snippet_updates} thread snippet update(s)")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry))
