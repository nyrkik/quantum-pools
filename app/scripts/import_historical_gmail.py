"""Import pre-cutover Sapphire Gmail threads into QP as historical context.

QP's initial_sync window is 30 days, so the ~4,000 DMS-imported messages
sitting in Gmail (from Zoho migration + pre-cutover personal-Gmail POP3
puller) never made it into the DB. Brian wants ConAm's customer page to
show 2024-2026 threads when you open it, not just the last month.

This script walks Gmail threadIds `before:2026/04/09 -in:trash` and
inserts every thread as `is_historical=True, status='handled'`. No
keep-filter — bulk-sender + vendor-automation threads are ingested too
so they remain searchable inside QP (e.g., "when did Cloudflare bill
me"). Zero AI — no orchestrator, no classifier, no drafter, no
AgentLearningService, no platform events, no notifications.

One Gmail thread = one AgentThread. Gmail threadId drives the
AgentThread.thread_key (`hist|<gmail_thread_id>`) so:
  - it's globally unique (no collision with live inbox thread_keys)
  - the script is idempotent on re-run (UPSERT semantics via unique key)

Messages are deduped by `rfc_message_id` — both within a thread and
across existing DB rows (if live ingest already captured a message, we
skip it here).

Per-message ``received_by_email`` is derived from the RFC headers in
precedence order: Delivered-To → To → Cc → outbound-From. Per-thread
``primary_owner_email`` is the mode of its messages' owners (tiebreak:
most recent message). Email string not user_id — the future user-inbox
feature will map email → user via one table when built.

Customer matching is direct-only (Customer.email exact + CustomerContact
email exact). Fuzzy matching + Claude verification are skipped to keep
token cost at zero; if a historical thread doesn't auto-match, it still
shows up on the customer page via manual customer_id assignment later,
or via the live-ingest fuzzy matcher the next time that sender emails.

-----------------------------------------------------------------------
USAGE:

    # Preview — counts + per-bucket dropped reasons, no writes
    ./venv/bin/python app/scripts/import_historical_gmail.py --dry-run

    # Narrow to a date range (handy for incremental re-runs)
    ./venv/bin/python app/scripts/import_historical_gmail.py \\
        --since 2024/01/01 --dry-run

    # Live run
    ./venv/bin/python app/scripts/import_historical_gmail.py

-----------------------------------------------------------------------
PRE-REQS:

- OAuth token from the cleanup script already exists at
  ~/.config/qp-sapphire-cleanup/token.json (gmail.modify scope — covers
  read). If not, run cleanup_sapphire_mailbox.py --pass=auth first.
- Sapphire is hardcoded as the target org since this is a one-shot
  migration. Override with --org-id if ever reused.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from src.core.database import get_db_context  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.models.agent_thread import AgentThread  # noqa: E402
from src.models.customer import Customer  # noqa: E402
from src.models.customer_contact import CustomerContact  # noqa: E402


SAPPHIRE_ORG_ID = "7ef7ab72-703f-45c1-847f-565101cb3e61"
CUTOVER_DATE = "2026/04/09"
TOKEN_PATH = Path.home() / ".config" / "qp-sapphire-cleanup" / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Keep-filter — employee addresses (exact email, lowercase). Any
# message in a thread matching one of these counts as "employee touched".
EMPLOYEE_EMAILS = frozenset({
    "brian@sapphire-pools.com",
    "kim@sapphire-pools.com",
    "chance@sapphire-pools.com",
    "shane@sapphire-pools.com",
    "contact@sapphire-pools.com",
    "accounting@sapphire-pools.com",
    "billing@sapphire-pools.com",  # pre-consolidation alias
    "info@sapphire-pools.com",
    "sales@sapphire-pools.com",
    "support@sapphire-pools.com",
    "sapphpools@gmail.com",  # legacy pre-Workspace mailbox
})

# Drop thread if every external (non-employee) party is a bulk sender.
# Matched on the local part of the email (before @).
BULK_LOCAL_PARTS = frozenset({
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "mailerdaemon", "postmaster",
    "newsletter", "marketing", "updates", "notifications",
    "notification", "alerts", "bounce", "bounces",
})

# Domains that are pure infra / never represent a real customer
# conversation (even when the localpart isn't obviously bulk).
INFRA_DOMAINS = frozenset({
    "mailer-daemon.google.com",
    "googlemail.com",  # rare Gmail variant, usually automated
    "mailchimp.com", "mcsv.net",
    "intuit.com", "quickbooks.com",
    "cloudflare.com", "cloudflareclient.com",
    "postmarkapp.com", "postmark.com",
    "stripe.com",  # Stripe receipts are noise; real customer mail comes from customer domain
})


# ---------- OAuth ----------

def load_token() -> Credentials:
    if not TOKEN_PATH.exists():
        sys.exit(
            f"Token not found at {TOKEN_PATH}. Run:\n"
            f"  ./venv/bin/python app/scripts/cleanup_sapphire_mailbox.py --pass=auth"
        )
    data = json.loads(TOKEN_PATH.read_text())
    expiry = None
    if data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(data["expiry"])
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except Exception:
            expiry = None
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or SCOPES,
        expiry=expiry,
    )
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# ---------- Gmail helpers ----------

def list_thread_ids(svc, query: str) -> list[str]:
    ids: list[str] = []
    page_token: str | None = None
    while True:
        resp = svc.users().threads().list(
            userId="me", q=query, maxResults=500, pageToken=page_token,
            includeSpamTrash=False,
        ).execute()
        for t in resp.get("threads", []):
            ids.append(t["id"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_thread(svc, thread_id: str, attempt: int = 0) -> dict | None:
    """Fetch a single thread with all messages (format=full). Retries on
    transient errors with exponential backoff."""
    try:
        return svc.users().threads().get(
            userId="me", id=thread_id, format="full",
        ).execute()
    except HttpError as e:
        msg = str(e)
        retryable = (
            "429" in msg or "500" in msg or "503" in msg
            or "rateLimit" in msg.lower() or "backendError" in msg
            or "unavailable" in msg.lower()
        )
        if retryable and attempt < 5:
            wait_s = min(2 ** attempt, 60)
            time.sleep(wait_s)
            return fetch_thread(svc, thread_id, attempt + 1)
        print(f"  warn: thread {thread_id} fetch failed ({e}), skipping")
        return None


# ---------- header + body parsing ----------

def _hdr(headers: list[dict], name: str) -> str:
    """Case-insensitive header lookup. Returns last matching value (RFC
    permits multiples; last-wins mirrors what MUAs display)."""
    needle = name.lower()
    for h in reversed(headers):
        if h.get("name", "").lower() == needle:
            return h.get("value", "")
    return ""


def _all_hdr(headers: list[dict], name: str) -> list[str]:
    """All values for a header (Delivered-To can appear multiple times)."""
    needle = name.lower()
    return [h.get("value", "") for h in headers if h.get("name", "").lower() == needle]


def _parse_addr_list(value: str) -> list[tuple[str, str]]:
    """Parse a header value into [(display_name, email_lower)] list.
    Silently drops unparseable entries."""
    if not value:
        return []
    out: list[tuple[str, str]] = []
    for name, addr in getaddresses([value]):
        addr = (addr or "").strip().lower()
        if "@" not in addr:
            continue
        out.append((name or "", addr))
    return out


def _single_addr(value: str) -> tuple[str, str]:
    """Parse a From-like single-address header. Returns (display, email)."""
    addrs = _parse_addr_list(value)
    if addrs:
        return addrs[0]
    return ("", "")


def _is_bulk_or_infra(email: str) -> bool:
    if "@" not in email:
        return True
    local, _, domain = email.partition("@")
    if local in BULK_LOCAL_PARTS:
        return True
    if domain in INFRA_DOMAINS:
        return True
    # Bluehost/cloudfilter relay noise — cloudfilter.net showed up on
    # DMARC reports, treat as infra.
    if domain.endswith(".cloudfilter.net"):
        return True
    return False


def _walk_parts(part: dict) -> Iterable[dict]:
    """Yield every MIME part in a message payload (depth-first)."""
    yield part
    for sub in (part.get("parts") or []):
        yield from _walk_parts(sub)


def _decode_body(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_bodies(payload: dict) -> tuple[str, str]:
    """Return (plain_text, html) from a message payload. Picks the first
    text/plain and first text/html encountered. Strips no further."""
    plain = ""
    html = ""
    for part in _walk_parts(payload or {}):
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data", "")
        if not data:
            continue
        if mime == "text/plain" and not plain:
            plain = _decode_body(data)
        elif mime == "text/html" and not html:
            html = _decode_body(data)
        if plain and html:
            break
    return plain, html


def parse_date(value: str, fallback_ms: str | None = None) -> datetime:
    """Parse the Date header; fall back to Gmail's internalDate."""
    if value:
        try:
            dt = parsedate_to_datetime(value)
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
        except Exception:
            pass
    if fallback_ms:
        try:
            return datetime.fromtimestamp(int(fallback_ms) / 1000, tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


# ---------- per-message owner ----------

def derive_owner(headers: list[dict], direction: str) -> str | None:
    """Per-message owner derivation. First hit wins:
      1. Delivered-To header that is an employee address
      2. To address that is an employee
      3. Cc address that is an employee
      4. Outbound: From if employee
    Returns None if no employee touched this message."""
    for dt in _all_hdr(headers, "Delivered-To"):
        for _, addr in _parse_addr_list(dt):
            if addr in EMPLOYEE_EMAILS:
                return addr
    for _, addr in _parse_addr_list(_hdr(headers, "To")):
        if addr in EMPLOYEE_EMAILS:
            return addr
    for _, addr in _parse_addr_list(_hdr(headers, "Cc")):
        if addr in EMPLOYEE_EMAILS:
            return addr
    if direction == "outbound":
        _, addr = _single_addr(_hdr(headers, "From"))
        if addr in EMPLOYEE_EMAILS:
            return addr
    return None


# ---------- keep-filter ----------

def extract_thread_parties(messages: list[dict]) -> tuple[set[str], set[str]]:
    """Return (employee_addrs, external_addrs) seen on any header (From,
    To, Cc, Delivered-To) across every message. Both sets are
    lowercase email strings."""
    employees: set[str] = set()
    external: set[str] = set()
    for m in messages:
        headers = (m.get("payload") or {}).get("headers") or []
        fields = ["From", "To", "Cc", "Delivered-To"]
        for f in fields:
            values = _all_hdr(headers, f) if f == "Delivered-To" else [_hdr(headers, f)]
            for v in values:
                for _, addr in _parse_addr_list(v):
                    if addr in EMPLOYEE_EMAILS:
                        employees.add(addr)
                    else:
                        external.add(addr)
    return employees, external


def thread_should_keep(messages: list[dict]) -> tuple[bool, str]:
    """Decide whether to ingest this Gmail thread. Returns (keep, reason)
    where reason is the drop bucket if keep=False."""
    employees, external = extract_thread_parties(messages)
    if not employees:
        return False, "no_employee"
    # Needs at least one non-bulk/non-infra external address.
    real_external = [a for a in external if not _is_bulk_or_infra(a)]
    if not real_external:
        return False, "bulk_only"
    return True, "keep"


# ---------- DB persistence ----------

async def match_customer_direct(
    db, org_id: str, sender_email: str,
) -> tuple[str | None, str | None, str | None]:
    """Direct customer match — no AI, no fuzzy. Returns
    (customer_id, customer_name, match_method)."""
    sender_lower = sender_email.lower()
    if not sender_lower:
        return None, None, None

    # 1. Customer.email (comma-separated field — LIKE match then exact
    # check on any comma-split token).
    result = await db.execute(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.is_active == True,  # noqa: E712
            func.lower(Customer.email).contains(sender_lower),
        ).limit(10)
    )
    for c in result.scalars().all():
        tokens = [e.strip().lower() for e in (c.email or "").split(",") if e.strip()]
        if sender_lower in tokens:
            return c.id, c.display_name, "email"

    # 2. CustomerContact.email
    contact = (await db.execute(
        select(CustomerContact).where(
            func.lower(CustomerContact.email) == sender_lower,
        ).limit(1)
    )).scalar_one_or_none()
    if contact:
        cust = (await db.execute(
            select(Customer).where(
                Customer.id == contact.customer_id,
                Customer.organization_id == org_id,
                Customer.is_active == True,  # noqa: E712
            )
        )).scalar_one_or_none()
        if cust:
            return cust.id, cust.display_name, "contact_email"

    return None, None, None


async def existing_rfc_ids(db, org_id: str) -> set[str]:
    """Return all rfc_message_ids already in the DB for this org, for
    dedup. Stripped of angle brackets, lowercased."""
    rows = await db.execute(
        select(AgentMessage.rfc_message_id).where(
            AgentMessage.organization_id == org_id,
            AgentMessage.rfc_message_id.is_not(None),
        )
    )
    return {
        (r[0] or "").strip().strip("<>").lower()
        for r in rows.all()
        if r[0]
    }


async def existing_thread_keys(db, org_id: str) -> set[str]:
    rows = await db.execute(
        select(AgentThread.thread_key).where(
            AgentThread.organization_id == org_id,
            AgentThread.is_historical == True,  # noqa: E712
        )
    )
    return {r[0] for r in rows.all()}


def normalize_rfc_id(value: str) -> str:
    return (value or "").strip().strip("<>").lower()


def thread_key_for(gmail_thread_id: str) -> str:
    return f"hist|{gmail_thread_id}"


# ---------- per-thread ingest ----------

async def ingest_thread(
    db, org_id: str, gmail_thread: dict, seen_rfc_ids: set[str],
    dry_run: bool,
) -> dict:
    """Ingest one Gmail thread. Returns stats dict. Mutates seen_rfc_ids
    so subsequent threads in the same run skip already-inserted messages."""
    gmail_thread_id = gmail_thread["id"]
    messages = gmail_thread.get("messages") or []
    tkey = thread_key_for(gmail_thread_id)

    # No keep-filter — everything pre-cutover is ingested so it's searchable
    # inside QP without bouncing out to Gmail. Threads matching old bulk-only
    # criteria still get inserted; they're invisible in triage (is_historical=True)
    # and discoverable via customer pages, All Mail folder, and search.

    # Pre-build per-message records. Skip messages already in DB by rfc_id
    # or duplicates within the same thread.
    candidates: list[dict] = []
    thread_owner_votes: list[str] = []
    contact_email_candidate = ""
    first_subject = ""
    for m in messages:
        payload = m.get("payload") or {}
        headers = payload.get("headers") or []

        from_name, from_email = _single_addr(_hdr(headers, "From"))
        to_hdr = _hdr(headers, "To")
        cc_hdr = _hdr(headers, "Cc")
        subject = _hdr(headers, "Subject")
        rfc_id_raw = _hdr(headers, "Message-Id") or _hdr(headers, "Message-ID")
        rfc_id = normalize_rfc_id(rfc_id_raw)
        date_hdr = _hdr(headers, "Date")
        delivered_to_values = _all_hdr(headers, "Delivered-To")
        # Pick the first employee Delivered-To if any, else the first one.
        delivered_to_pick = ""
        for dv in delivered_to_values:
            _, addr = _single_addr(dv)
            if addr in EMPLOYEE_EMAILS:
                delivered_to_pick = addr
                break
        if not delivered_to_pick and delivered_to_values:
            _, delivered_to_pick = _single_addr(delivered_to_values[0])

        # Direction — outbound if From is an employee address.
        direction = "outbound" if from_email in EMPLOYEE_EMAILS else "inbound"
        received_by = derive_owner(headers, direction)
        if received_by:
            thread_owner_votes.append(received_by)

        # Dedup at run-level (already in DB or already queued this thread).
        if rfc_id and rfc_id in seen_rfc_ids:
            continue

        plain, html = extract_bodies(payload)
        received_at = parse_date(date_hdr, m.get("internalDate"))

        if not first_subject and subject:
            first_subject = subject
        # Prefer the most recent inbound external sender as contact_email.
        if direction == "inbound" and from_email and not _is_bulk_or_infra(from_email):
            contact_email_candidate = from_email

        candidates.append({
            "rfc_id": rfc_id,
            "from_email": from_email,
            "from_name": from_name or None,
            "to_email": to_hdr[:255],
            "cc_hdr": cc_hdr,
            "subject": subject,
            "body": plain,
            "body_html": html,
            "direction": direction,
            "received_at": received_at,
            "delivered_to": delivered_to_pick[:255] if delivered_to_pick else None,
            "received_by": received_by,
        })
        if rfc_id:
            seen_rfc_ids.add(rfc_id)

    if not candidates:
        # Every message already ingested via live pipeline — nothing to do.
        return {"action": "skipped_all_dup", "messages": 0}

    # contact_email fallback — first external sender we saw.
    if not contact_email_candidate:
        for c in candidates:
            if c["from_email"] and c["from_email"] not in EMPLOYEE_EMAILS:
                contact_email_candidate = c["from_email"]
                break
    if not contact_email_candidate:
        # all employees — pick first From, whatever it is
        contact_email_candidate = candidates[0]["from_email"] or "unknown@historical"

    # Subject fallback.
    subject_final = first_subject or "(no subject)"

    # primary_owner_email = mode of per-message owners; tiebreak by
    # most recent message's owner.
    if thread_owner_votes:
        counts = Counter(thread_owner_votes)
        top_count = counts.most_common(1)[0][1]
        tied = [owner for owner, c in counts.items() if c == top_count]
        if len(tied) == 1:
            primary_owner = tied[0]
        else:
            # Tiebreak — walk messages newest-first, pick first tied owner.
            primary_owner = None
            for c in sorted(candidates, key=lambda x: x["received_at"], reverse=True):
                if c["received_by"] in tied:
                    primary_owner = c["received_by"]
                    break
    else:
        primary_owner = None

    # Customer match from the thread's external contact.
    cust_id, cust_name, match_method = await match_customer_direct(
        db, org_id, contact_email_candidate,
    )

    last_msg = max(candidates, key=lambda x: x["received_at"])
    last_direction = last_msg["direction"]
    first_msg = min(candidates, key=lambda x: x["received_at"])

    if dry_run:
        return {
            "action": "would_insert",
            "messages": len(candidates),
            "matched_customer": bool(cust_id),
            "subject": subject_final[:60],
            "contact": contact_email_candidate,
        }

    # Insert thread.
    thread = AgentThread(
        organization_id=org_id,
        thread_key=tkey,
        contact_email=contact_email_candidate[:255],
        subject=subject_final[:500],
        matched_customer_id=cust_id,
        customer_name=cust_name,
        status="handled",  # terminal — doesn't queue for AI
        message_count=len(candidates),
        last_message_at=last_msg["received_at"],
        last_direction=last_direction,
        last_snippet=(last_msg["body"] or "")[:200],
        has_pending=False,
        has_open_actions=False,
        gmail_thread_id=gmail_thread_id,
        delivered_to=first_msg["delivered_to"],
        is_historical=True,
        primary_owner_email=primary_owner,
        created_at=first_msg["received_at"],
    )
    db.add(thread)
    await db.flush()

    for c in candidates:
        # email_uid column is varchar(100). Outlook/Exchange Message-IDs
        # routinely exceed 80 chars on their own, so hash the full identity
        # to a fixed short form that still keeps the `hist-` prefix
        # (distinguishable from `gm-`/`pm-` live-ingest UIDs).
        uid_seed = f"{gmail_thread_id}|{c['rfc_id'] or 'noid'}|{int(c['received_at'].timestamp())}"
        uid_hash = hashlib.sha1(uid_seed.encode("utf-8")).hexdigest()
        msg = AgentMessage(
            organization_id=org_id,
            email_uid=f"hist-{uid_hash}",
            rfc_message_id=c["rfc_id"] or None,
            direction=c["direction"],
            from_email=(c["from_email"] or "unknown@historical")[:255],
            from_name=c["from_name"][:200] if c["from_name"] else None,
            to_email=c["to_email"],
            subject=(c["subject"] or "")[:500],
            body=(c["body"] or "")[:50000],
            body_html=(c["body_html"] or None) if c["body_html"] else None,
            status="ignored" if c["direction"] == "inbound" else "sent",
            matched_customer_id=cust_id,
            match_method=match_method,
            customer_name=cust_name,
            delivered_to=c["delivered_to"],
            received_by_email=c["received_by"],
            thread_id=thread.id,
            received_at=c["received_at"],
            created_at=c["received_at"],
        )
        db.add(msg)

    await db.commit()
    return {
        "action": "inserted",
        "messages": len(candidates),
        "matched_customer": bool(cust_id),
    }


# ---------- main ----------

async def run(org_id: str, since: str | None, dry_run: bool, limit: int | None) -> None:
    creds = load_token()
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    profile = svc.users().getProfile(userId="me").execute()
    print(f"Mailbox: {profile.get('emailAddress')}  (total msgs: {profile.get('messagesTotal')})")
    print(f"Target org: {org_id}")
    if dry_run:
        print("DRY RUN — no writes.\n")

    # Build Gmail query.
    q_parts = [f"before:{CUTOVER_DATE}", "-in:trash"]
    if since:
        q_parts.append(f"after:{since}")
    query = " ".join(q_parts)
    print(f"Gmail query: {query}")

    thread_ids = list_thread_ids(svc, query)
    print(f"Gmail threads to scan: {len(thread_ids)}")
    if limit is not None:
        thread_ids = thread_ids[:limit]
        print(f"  (limited to first {limit})")

    async with get_db_context() as db:
        seen_rfc_ids = await existing_rfc_ids(db, org_id)
        existing_keys = await existing_thread_keys(db, org_id)
        print(f"Already-ingested rfc_message_ids in DB: {len(seen_rfc_ids)}")
        print(f"Historical threads already in DB: {len(existing_keys)}")

        stats = Counter()
        inserted_msgs = 0
        for idx, tid in enumerate(thread_ids, 1):
            if tid in {k.removeprefix("hist|") for k in existing_keys} and not dry_run:
                # Already-ingested thread — skip to keep re-runs fast.
                stats["skip_already_ingested"] += 1
                continue
            gt = fetch_thread(svc, tid)
            if not gt:
                stats["fetch_fail"] += 1
                continue
            res = await ingest_thread(db, org_id, gt, seen_rfc_ids, dry_run)
            stats[res["action"]] += 1
            if res.get("reason"):
                stats[f"drop_{res['reason']}"] += 1
            if res["action"] in ("inserted", "would_insert"):
                inserted_msgs += res["messages"]
                if res.get("matched_customer"):
                    stats["matched_customer"] += 1
            if idx % 50 == 0:
                print(f"  ...{idx}/{len(thread_ids)} threads scanned")

        print("\n=== Summary ===")
        for k in sorted(stats):
            print(f"  {k}: {stats[k]}")
        print(f"  messages {'would be inserted' if dry_run else 'inserted'}: {inserted_msgs}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Preview; no writes.")
    ap.add_argument("--org-id", default=SAPPHIRE_ORG_ID,
                    help="Target organization id (default: Sapphire).")
    ap.add_argument("--since", default=None,
                    help="Gmail after:YYYY/MM/DD lower bound (default: no lower bound).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit to first N threads (debugging).")
    args = ap.parse_args()
    asyncio.run(run(args.org_id, args.since, args.dry_run, args.limit))


if __name__ == "__main__":
    main()
