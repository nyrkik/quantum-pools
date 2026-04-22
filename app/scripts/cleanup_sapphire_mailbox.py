"""Clean up the Sapphire Gmail mailbox after the Zoho DMS migration.

Three independent passes, each with its own --dry-run preview:

    Pass 1 — Unlabel Zoho-*
        Removes Zoho-Brian, Zoho-Kim, Zoho-Chance labels from every message,
        then deletes the labels themselves. The per-mailbox labels were
        scaffolding for the junk-cleanup pass; no longer useful.

    Pass 2 — Dedupe by Message-ID
        Groups every message in the mailbox by RFC 822 Message-Id header.
        When >1 message shares the same Message-Id (DMS imported the same
        CC'd email into multiple source mailboxes, or POP3 puller + DMS
        both stored the same mail), trashes all but the oldest.

    Pass 3 — Junk sweep (historical)
        Runs a narrow junk search once across all pre-cutover mail:
        `before:2026/04/09 -label:QP-Processed -label:Sapphire
        category:promotions` → trash.
        Intentionally narrow — noreply-sender matching swept up
        transactional mail (Stripe/bank/shipping); Gmail's promotions
        classifier is conservative enough on its own.

All destructive actions move messages to Trash (30-day auto-recovery).
Re-running is safe: Pass 1 is idempotent; Pass 2 skips already-unique
message-ids; Pass 3 excludes already-trashed.

-----------------------------------------------------------------------
ONE-TIME SETUP (before first run):

1) GCP console (project `quantumpools-oauth`) → APIs & Services →
   Credentials → Create Credentials → OAuth client ID → Application
   type: Desktop app. Desktop clients natively support localhost
   redirects — no URI configuration needed.

   Add the new client's id+secret to app/.env as:
        GMAIL_CLEANUP_CLIENT_ID=...
        GMAIL_CLEANUP_CLIENT_SECRET=...

   Keep this separate from QP's production Web OAuth client
   (GOOGLE_OAUTH_CLIENT_ID/SECRET).

2) Run with --pass=auth on a machine where you can open a browser:

        ./venv/bin/python app/scripts/cleanup_sapphire_mailbox.py --pass=auth

   If running over SSH, open an SSH tunnel first from your workstation:

        ssh -L 8765:localhost:8765 brian@100.121.52.15

   Script prints the consent URL; visit in browser, grant access as
   brian@sapphire-pools.com, token is cached to
   ~/.config/qp-sapphire-cleanup/token.json.

-----------------------------------------------------------------------
USAGE:

    # Preview every pass without changing anything
    ./venv/bin/python app/scripts/cleanup_sapphire_mailbox.py --dry-run

    # Run a single pass (live)
    ./venv/bin/python app/scripts/cleanup_sapphire_mailbox.py --pass=2

    # Run everything live
    ./venv/bin/python app/scripts/cleanup_sapphire_mailbox.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from google_auth_oauthlib.flow import Flow  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
LOCAL_PORT = 8765
REDIRECT_URI = f"http://localhost:{LOCAL_PORT}/"
TOKEN_DIR = Path.home() / ".config" / "qp-sapphire-cleanup"
TOKEN_PATH = TOKEN_DIR / "token.json"

ZOHO_LABELS = ["Zoho-Brian", "Zoho-Kim", "Zoho-Chance"]
CUTOVER_DATE = "2026/04/09"


# ---------- auth ----------

def _client_config() -> dict:
    cid = os.environ.get("GMAIL_CLEANUP_CLIENT_ID", "").strip()
    csec = os.environ.get("GMAIL_CLEANUP_CLIENT_SECRET", "").strip()
    if not cid or not csec:
        sys.exit("GMAIL_CLEANUP_CLIENT_ID / GMAIL_CLEANUP_CLIENT_SECRET missing from app/.env")
    return {
        "installed": {
            "client_id": cid,
            "client_secret": csec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [REDIRECT_URI],
        }
    }


def _save_token(creds: Credentials) -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }))
    os.chmod(TOKEN_PATH, 0o600)


def _load_token() -> Credentials | None:
    if not TOKEN_PATH.exists():
        return None
    data = json.loads(TOKEN_PATH.read_text())
    from datetime import datetime
    expiry = None
    if data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(data["expiry"])
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except Exception:
            expiry = None
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or SCOPES,
        expiry=expiry,
    )


def run_auth_flow() -> Credentials:
    """Interactive OAuth consent via paste-back. Prints URL; user opens in
    browser, signs in, and pastes the final redirected URL back. Works
    without any localhost reachability (handy when SSH port-forwarding is
    unavailable)."""
    from urllib.parse import urlparse, parse_qs

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("Open this URL in a browser and grant access as brian@sapphire-pools.com:\n")
    print(f"    {auth_url}\n")
    print(
        "After you approve, Google will redirect to http://localhost:8765/... —\n"
        "that page WILL fail to load (expected; nothing is listening). Copy the FULL\n"
        "redirected URL from your browser's address bar and paste it below.\n"
    )
    pasted = input("Paste redirected URL here: ").strip()
    if not pasted:
        sys.exit("No URL pasted.")

    parsed = urlparse(pasted)
    qs = parse_qs(parsed.query)
    code = (qs.get("code") or [None])[0]
    if not code:
        sys.exit(f"No ?code=... found in pasted URL. Got query: {parsed.query!r}")

    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_token(creds)
    print(f"Token saved to {TOKEN_PATH}")
    return creds


def get_credentials() -> Credentials:
    creds = _load_token()
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds
    return run_auth_flow()


# ---------- gmail helpers ----------

def list_all_message_ids(svc, query: str) -> list[str]:
    """Walk full pagination of users.messages.list for `query`.
    Returns all matching message IDs."""
    ids: list[str] = []
    page_token: str | None = None
    while True:
        resp = svc.users().messages().list(
            userId="me", q=query, maxResults=500, pageToken=page_token,
            includeSpamTrash=False,
        ).execute()
        for m in resp.get("messages", []):
            ids.append(m["id"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def batch_modify(svc, ids: list[str], add: list[str] | None = None,
                 remove: list[str] | None = None, chunk: int = 1000) -> None:
    """Call users.messages.batchModify in chunks of 1000 (API cap)."""
    if not ids:
        return
    for i in range(0, len(ids), chunk):
        body = {"ids": ids[i:i + chunk]}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        svc.users().messages().batchModify(userId="me", body=body).execute()


def fetch_metadata_batch(svc, ids: list[str], headers: list[str]) -> dict[str, dict]:
    """Fetch format=metadata (headers only) for each id. Returns {id: message}.
    Uses BatchHttpRequest with smaller chunks + exponential-backoff retry.

    Gmail's "concurrent requests per user" cap is much tighter than its
    per-second quota. BatchHttpRequest of 100 counts as 100 concurrent,
    which bursts over the cap even though the per-second budget is fine.
    Smaller batch + backoff keeps us inside both limits.
    """
    out: dict[str, dict] = {}
    remaining = list(ids)
    attempt = 0
    MAX_ATTEMPTS = 6
    CHUNK = 25

    while remaining and attempt < MAX_ATTEMPTS:
        failed: list[str] = []

        def _cb(request_id, response, exception):
            if exception:
                msg = str(exception)
                # Retry on rate-limit (429), backend-errors (500/503), and concurrent-cap.
                # Only give up on genuine client errors (404, 403, etc.)
                retryable = (
                    "429" in msg or "500" in msg or "503" in msg
                    or "rateLimit" in msg.lower() or "concurrent" in msg.lower()
                    or "backendError" in msg or "unavailable" in msg.lower()
                )
                if retryable:
                    failed.append(request_id)
                else:
                    print(f"  warn (non-retryable): {request_id}: {exception}")
                return
            out[request_id] = response

        for i in range(0, len(remaining), CHUNK):
            batch = svc.new_batch_http_request(callback=_cb)
            for mid in remaining[i:i + CHUNK]:
                batch.add(
                    svc.users().messages().get(
                        userId="me", id=mid, format="metadata", metadataHeaders=headers,
                    ),
                    request_id=mid,
                )
            batch.execute()
            time.sleep(0.5)

        if not failed:
            break

        wait_s = min(2 ** attempt, 60)
        print(f"  retrying {len(failed)} rate-limited messages in {wait_s}s "
              f"(attempt {attempt + 1}/{MAX_ATTEMPTS})")
        time.sleep(wait_s)
        remaining = failed
        attempt += 1

    if remaining:
        print(f"  warn: {len(remaining)} messages still unfetched after {MAX_ATTEMPTS} retries")
    return out


def get_label_map(svc) -> dict[str, str]:
    """Return {label_name: label_id} for user labels."""
    resp = svc.users().labels().list(userId="me").execute()
    return {lbl["name"]: lbl["id"] for lbl in resp.get("labels", [])}


# ---------- passes ----------

def pass1_unlabel(svc, dry_run: bool) -> None:
    print("\n=== Pass 1: remove Zoho-* labels ===")
    label_map = get_label_map(svc)
    for name in ZOHO_LABELS:
        lid = label_map.get(name)
        if not lid:
            print(f"  {name}: not present, skip")
            continue
        ids = list_all_message_ids(svc, f"label:{name}")
        print(f"  {name}: {len(ids)} messages")
        if not dry_run and ids:
            batch_modify(svc, ids, remove=[lid])
        if not dry_run:
            try:
                svc.users().labels().delete(userId="me", id=lid).execute()
                print(f"  {name}: label deleted")
            except HttpError as e:
                print(f"  {name}: delete failed ({e})")


def pass2_dedupe(svc, dry_run: bool) -> None:
    print("\n=== Pass 2: dedupe by Message-ID ===")
    # Scope: all non-trashed, non-sent-drafts mail. We intentionally scan the
    # whole mailbox (not just pre-cutover) since POP3 puller may have made
    # dupes of mail received after cutover too.
    ids = list_all_message_ids(svc, "-in:trash -in:draft")
    print(f"  total messages to scan: {len(ids)}")

    print("  fetching Message-Id headers...")
    metas = fetch_metadata_batch(svc, ids, headers=["Message-Id"])

    # Group by Message-Id (case-insensitive, stripped angle brackets).
    groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    no_header = 0
    for mid, msg in metas.items():
        hdrs = (msg.get("payload") or {}).get("headers") or []
        mid_hdr = next((h["value"] for h in hdrs if h.get("name", "").lower() == "message-id"), None)
        if not mid_hdr:
            no_header += 1
            continue
        key = mid_hdr.strip().strip("<>").lower()
        internal_date = int(msg.get("internalDate") or 0)
        groups[key].append((mid, internal_date))

    print(f"  unique message-ids: {len(groups)}")
    print(f"  messages with no Message-Id header: {no_header} (cannot dedupe, left alone)")

    # For each group > 1, keep oldest (smallest internalDate), trash rest.
    to_trash: list[str] = []
    for key, entries in groups.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda t: t[1])  # oldest first
        _keep, *dupes = entries
        to_trash.extend(did for did, _ in dupes)

    print(f"  duplicates identified: {len(to_trash)}")
    if dry_run:
        print("  (dry-run — nothing trashed)")
        return
    if not to_trash:
        return

    # Trash via batchModify: add TRASH, remove INBOX + UNREAD for cleanliness.
    # Gmail's dedicated trash() per-message would cost 10u × N; batchModify = 50u/chunk.
    print(f"  trashing {len(to_trash)} duplicates...")
    batch_modify(svc, to_trash, add=["TRASH"], remove=["INBOX", "UNREAD"])
    print("  done.")


def pass3_junk(svc, dry_run: bool) -> None:
    print("\n=== Pass 3: junk sweep (historical, pre-cutover) ===")
    # category:promotions only — narrow + high-precision. Noreply-sender filtering
    # was too aggressive (Stripe receipts, bank alerts, shipping notifications all
    # come from noreply@ and aren't junk). has:list-unsubscribe returned 0 on this
    # mailbox; likely DMS-imported mail didn't preserve the header for Gmail to
    # index.
    q = (
        f"before:{CUTOVER_DATE} -label:QP-Processed -label:Sapphire "
        f"category:promotions"
    )
    ids = list_all_message_ids(svc, q)
    print(f"  matches: {len(ids)}")
    if dry_run:
        print("  (dry-run — nothing trashed)")
        return
    if not ids:
        return
    batch_modify(svc, ids, add=["TRASH"], remove=["INBOX", "UNREAD"])
    print(f"  trashed {len(ids)}")


# ---------- main ----------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Preview each pass without any writes.")
    ap.add_argument("--pass", dest="which", default="all",
                    choices=["auth", "1", "2", "3", "all"],
                    help="Which pass to run (default: all).")
    args = ap.parse_args()

    if args.which == "auth":
        run_auth_flow()
        return

    creds = get_credentials()
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # Sanity check: show the account we're about to mutate.
    profile = svc.users().getProfile(userId="me").execute()
    print(f"Mailbox: {profile.get('emailAddress')}  ({profile.get('messagesTotal')} messages total)")
    if args.dry_run:
        print("DRY RUN — no changes will be made.\n")

    if args.which in ("1", "all"):
        pass1_unlabel(svc, args.dry_run)
    if args.which in ("2", "all"):
        pass2_dedupe(svc, args.dry_run)
    if args.which in ("3", "all"):
        pass3_junk(svc, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
