"""ThreadPresenter — single source of truth for AgentThread serialization.

Resolves:
- matched_customer_id → Customer.display_name (not raw customer_name)
- matched_customer_id → first Property address
"""

import re
from datetime import datetime

from src.presenters.base import Presenter
from src.models.agent_thread import AgentThread


_PAREN_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


# Heuristic: a local part that contains an underscore-separated hex
# blob or a hex run ≥16 chars is almost certainly a VERP / tracking
# mailbox (AmEx: ``r_07b156d0-...``, Poolcorp: ``b-1_3yyno...``). Show
# a pretty domain instead of the opaque local part.
_OPAQUE_LOCAL_RE = re.compile(
    r"^(?:[a-z]_[0-9a-f]{4,}|[a-z]+-\d+_[0-9a-z]{4,}|[0-9a-f]{16,})",
    re.IGNORECASE,
)


def _prettify_contact_email(email_addr: str | None) -> str | None:
    """When no better display name is available, produce one from the
    email address itself. Opaque local parts (VERP tracking mailboxes)
    get a domain-based display; everything else renders the email
    unchanged (the UI still shows it, and at least it's a real name
    for one-off human senders)."""
    if not email_addr or "@" not in email_addr:
        return email_addr
    local, _, domain = email_addr.rpartition("@")
    if _OPAQUE_LOCAL_RE.match(local):
        # "welcome.americanexpress.com" → "americanexpress.com"
        parts = domain.lower().split(".")
        if len(parts) >= 3 and parts[0] in {
            "welcome", "bounce", "bouncing", "mail", "email", "send",
            "notifications", "notify", "info", "updates",
        }:
            parts = parts[1:]
        return ".".join(parts)
    return email_addr


def clean_person_name(raw: str | None, forbidden: set[str]) -> str | None:
    """Strip trailing property/company suffixes from an AI-extracted name.

    Handles patterns like:
      "Gene (Pinebrook Village)"           → "Gene"
      "Caprice Goshko / Bridges at Woodcreek" → "Caprice Goshko"
      "Toshi Cordova — Willow Glen"        → "Toshi Cordova"
      "Terra Bella (BrightPM)"             → None  (bare property/company, no person)

    Returns None if what's left is empty, matches a forbidden org label, or is too
    short to be a real person name.
    """
    if not raw:
        return None
    s = raw.strip()
    # Repeatedly strip trailing parentheticals so "A (B) (C)" collapses fully.
    prev = None
    while prev != s:
        prev = s
        s = _PAREN_SUFFIX.sub("", s).strip()
    # Drop anything after a separator.
    for sep in ("/", "—", "–"):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    if not s or s.lower() in forbidden:
        return None
    return s


class ThreadPresenter(Presenter):
    """Present AgentThread data with resolved FKs."""

    async def many(self, threads: list[AgentThread], read_map: dict[str, datetime] | None = None) -> list[dict]:
        """Present a list of threads with batch-loaded customer data."""
        cust_ids = {t.matched_customer_id for t in threads if t.matched_customer_id}
        customers = await self._load_customers(cust_ids)
        addresses = await self._load_customer_addresses(cust_ids)

        # Batch-resolve per-thread person name (latest inbound sender — see helper).
        # Used to show "Org Name (Person)" — the person who actually replied vs. the account.
        contact_name_by_email = await self._load_contact_names(threads)

        # Batch-resolve the sender's From-header display name per thread
        # (e.g. "American Express" for VERP senders) — used as a
        # fallback when no customer matched + no customer_name.
        from_name_by_thread = await self._load_from_names(threads)

        # Batch-resolve the most recent OUTBOUND from_name per thread
        # so the row can show "Kim replied" when last_direction is
        # outbound (FB-50).
        last_outbound_by_thread = await self._load_last_outbound_from_names(threads)

        # Batch-resolve sender tags via InboxRulesService (unified rule engine).
        # Each unique sender is looked up once; thread-level assignment happens
        # in the per-thread loop below.
        sender_tag_by_email: dict[str, str] = {}
        if threads:
            from src.services.inbox_rules_service import InboxRulesService
            org_id = threads[0].organization_id
            svc = InboxRulesService(self.db)
            unique_senders = {t.contact_email.lower() for t in threads if t.contact_email}
            for sender in unique_senders:
                tag = await svc.get_sender_tag(sender, org_id)
                if tag:
                    sender_tag_by_email[sender] = tag

        results = []
        for t in threads:
            d = self._base(t)

            # Customer — always from source of truth
            cust = customers.get(t.matched_customer_id) if t.matched_customer_id else None
            if cust:
                d["customer_name"] = cust.display_name
                d["contact_name"] = t.customer_name if t.customer_name != cust.display_name else None
                d["customer_address"] = addresses.get(t.matched_customer_id)
            else:
                # No matched customer — fall back to the thread's
                # denormalized customer_name, then the latest From
                # header's display name ("American Express" for VERP),
                # then a VERP-aware pretty domain derived from the
                # contact email. Never leave this null if we have any
                # signal — the inbox row's top-line identity depends
                # on it.
                d["customer_name"] = (
                    t.customer_name
                    or from_name_by_thread.get(t.id)
                    or _prettify_contact_email(t.contact_email)
                )
                d["contact_name"] = None
                d["customer_address"] = None

            # Sender tag — already resolved via the rule engine above.
            d["sender_tag"] = (
                sender_tag_by_email.get(t.contact_email.lower())
                if t.contact_email
                else None
            )

            # Person-name (latest inbound sender), shown next to customer/org name.
            d["contact_person_name"] = contact_name_by_email.get(t.id)

            # Surface the team-member who last replied, so glancing at the
            # inbox shows "↑ Kim replied" without opening the thread (FB-50).
            d["last_outbound_from_name"] = last_outbound_by_thread.get(t.id)

            # Unread status — rule-driven auto_read_at silences threads that
            # matched a mark_as_read rule up to last_message_at. A later
            # message without the rule firing re-unreads the thread naturally.
            if read_map is not None:
                user_read = read_map.get(t.id)
                effective_read = max(
                    x for x in [user_read, t.auto_read_at] if x is not None
                ) if (user_read or t.auto_read_at) else None
                d["is_unread"] = (
                    (t.last_message_at > effective_read)
                    if effective_read and t.last_message_at
                    else t.last_message_at is not None
                )
            else:
                d["is_unread"] = False

            results.append(d)
        return results

    async def one(self, thread: AgentThread, user_id: str | None = None) -> dict:
        """Present a single thread with resolved customer data."""
        d = self._base(thread)

        if thread.matched_customer_id:
            customers = await self._load_customers({thread.matched_customer_id})
            addresses = await self._load_customer_addresses({thread.matched_customer_id})
            cust = customers.get(thread.matched_customer_id)
            if cust:
                d["customer_name"] = cust.display_name
                d["contact_name"] = thread.customer_name if thread.customer_name != cust.display_name else None
                d["customer_address"] = addresses.get(thread.matched_customer_id)
            else:
                d["customer_name"] = thread.customer_name
        else:
            # Same fallback chain as `many` — From-header display name,
            # then VERP-aware pretty domain, so an unmatched sender
            # never shows up as just an opaque email address.
            from_names = await self._load_from_names([thread])
            d["customer_name"] = (
                thread.customer_name
                or from_names.get(thread.id)
                or _prettify_contact_email(thread.contact_email)
            )

        # Unread status — honor rule-driven auto_read_at alongside ThreadRead.
        if user_id:
            from sqlalchemy import select
            from src.models.thread_read import ThreadRead
            read = (await self.db.execute(
                select(ThreadRead.read_at).where(
                    ThreadRead.thread_id == thread.id,
                    ThreadRead.user_id == user_id,
                )
            )).scalar_one_or_none()
            effective_read = max(
                x for x in [read, thread.auto_read_at] if x is not None
            ) if (read or thread.auto_read_at) else None
            d["is_unread"] = (
                (thread.last_message_at > effective_read)
                if effective_read and thread.last_message_at
                else thread.last_message_at is not None
            )
        else:
            d["is_unread"] = False

        # Auto-handled — two flags from the same source:
        #   `was_auto_handled` is sticky once the AI auto-closed the
        #     thread, and drives the "AI" row pill in every Handled view
        #     (so non-admins finally see AI's work).
        #   `is_auto_handled` is the not-yet-acked subset, drives the
        #     in-thread feedback banner. Clears once the user clicks
        #     Yes/No (sets auto_handled_feedback_at).
        d["was_auto_handled"] = thread.auto_handled_at is not None
        d["is_auto_handled"] = (
            thread.auto_handled_at is not None
            and thread.auto_handled_feedback_at is None
        )

        # Sender tag via the unified rule engine
        if thread.contact_email:
            from src.services.inbox_rules_service import InboxRulesService
            d["sender_tag"] = await InboxRulesService(self.db).get_sender_tag(
                thread.contact_email, thread.organization_id
            )
        else:
            d["sender_tag"] = None

        # Person-name from latest inbound message (or CustomerContact fallback)
        names = await self._load_contact_names([thread])
        d["contact_person_name"] = names.get(thread.id)

        # Last outbound team-member sender — see _load_last_outbound_from_names.
        last_out = await self._load_last_outbound_from_names([thread])
        d["last_outbound_from_name"] = last_out.get(thread.id)

        return d

    async def _load_last_outbound_from_names(
        self, threads: list[AgentThread],
    ) -> dict[str, str]:
        """Return `{thread_id: from_name}` for the most recent OUTBOUND
        message per thread.

        Powers the inbox row's "Replied by Kim" indicator (FB-50): when
        teammates can't see who on the team last replied without
        opening the thread, they double-handle replies. Falls back to
        nothing when the latest outbound has no from_name (very old
        rows); caller treats that as "we replied as the org" and
        renders nothing rather than a wrong attribution.
        """
        if not threads:
            return {}
        from sqlalchemy import select
        from src.models.agent_message import AgentMessage

        rows = (await self.db.execute(
            select(
                AgentMessage.thread_id, AgentMessage.from_name,
                AgentMessage.sent_at, AgentMessage.received_at,
            )
            .where(
                AgentMessage.thread_id.in_([t.id for t in threads]),
                AgentMessage.direction == "outbound",
                AgentMessage.status.in_(("sent", "auto_sent")),
                AgentMessage.from_name.is_not(None),
            )
            .order_by(
                AgentMessage.thread_id,
                AgentMessage.sent_at.desc().nullslast(),
                AgentMessage.received_at.desc(),
            )
        )).all()

        out: dict[str, str] = {}
        for tid, fname, _sent, _rec in rows:
            if tid not in out and fname and fname.strip() and "@" not in fname:
                out[tid] = fname.strip()
        return out

    async def _load_from_names(
        self, threads: list[AgentThread],
    ) -> dict[str, str]:
        """Return `{thread_id: from_name}` using the latest inbound
        message's ``AgentMessage.from_name`` when set. Legacy rows
        (ingested before the column existed) return nothing; the
        caller falls back to a domain prettifier."""
        if not threads:
            return {}
        from sqlalchemy import select
        from src.models.agent_message import AgentMessage

        rows = (await self.db.execute(
            select(
                AgentMessage.thread_id, AgentMessage.from_name,
                AgentMessage.received_at,
            )
            .where(
                AgentMessage.thread_id.in_([t.id for t in threads]),
                AgentMessage.direction == "inbound",
                AgentMessage.from_name.is_not(None),
            )
            .order_by(AgentMessage.thread_id, AgentMessage.received_at.desc())
        )).all()

        out: dict[str, str] = {}
        for tid, fname, _rec in rows:
            if tid not in out and fname and fname.strip():
                # Drop homograph-attack / noisy display names that are
                # just the email address ("brian@x.com" <brian@x.com>).
                if "@" not in fname:
                    out[tid] = fname.strip()
        return out

    async def _load_contact_names(self, threads: list[AgentThread]) -> dict[str, str]:
        """Batch-resolve person names per thread (keyed by thread.id).

        Preference order for each thread:
          1. Most-recent inbound AgentMessage.customer_name (AI-extracted at receive time).
          2. CustomerContact.first_name + last_name matched by (org, sender email).
        Values that equal the matched customer's display name are filtered out so we don't
        show "Coventry Park (Coventry Park)".
        """
        if not threads:
            return {}
        from sqlalchemy import select, func
        from src.models.customer_contact import CustomerContact
        from src.models.agent_message import AgentMessage
        from src.models.customer import Customer

        thread_ids = [t.id for t in threads]
        cust_ids = {t.matched_customer_id for t in threads if t.matched_customer_id}

        # Build the set of forbidden display names — org labels that must not be shown as person names.
        forbidden: set[str] = set()
        if cust_ids:
            cust_rows = (await self.db.execute(
                select(Customer.first_name, Customer.last_name, Customer.company_name).where(
                    Customer.id.in_(list(cust_ids))
                )
            )).all()
            for fn, ln, co in cust_rows:
                for val in [co, f"{fn or ''} {ln or ''}".strip()]:
                    if val:
                        forbidden.add(val.lower())

        # Most-recent inbound message per thread (one query, deduped in Python).
        msg_rows = (await self.db.execute(
            select(AgentMessage.thread_id, AgentMessage.from_email, AgentMessage.customer_name, AgentMessage.received_at)
            .where(
                AgentMessage.thread_id.in_(thread_ids),
                AgentMessage.direction == "inbound",
            )
            .order_by(AgentMessage.thread_id, AgentMessage.received_at.desc())
        )).all()
        latest_by_thread: dict[str, tuple[str | None, str | None]] = {}
        for tid, from_email, cname, _rec in msg_rows:
            if tid not in latest_by_thread:
                latest_by_thread[tid] = (from_email, cname)

        # CustomerContact fallback — batch by org.
        by_org: dict[str, set[str]] = {}
        for tid, (from_email, _) in latest_by_thread.items():
            if from_email:
                org = next((t.organization_id for t in threads if t.id == tid), None)
                if org:
                    by_org.setdefault(org, set()).add(from_email.lower())
        contact_name_by_email: dict[tuple[str, str], str] = {}
        for org_id, emails in by_org.items():
            rows = (await self.db.execute(
                select(CustomerContact).where(
                    CustomerContact.organization_id == org_id,
                    func.lower(CustomerContact.email).in_(list(emails)),
                )
            )).scalars().all()
            for c in rows:
                if not c.email:
                    continue
                name = " ".join(filter(None, [c.first_name, c.last_name])).strip()
                cleaned = clean_person_name(name, forbidden)
                if cleaned:
                    contact_name_by_email[(org_id, c.email.lower())] = cleaned

        out: dict[str, str] = {}
        for t in threads:
            from_email, msg_cname = latest_by_thread.get(t.id, (None, None))
            cleaned = clean_person_name(msg_cname, forbidden)
            if cleaned:
                out[t.id] = cleaned
            elif from_email:
                fallback = contact_name_by_email.get((t.organization_id, from_email.lower()))
                if fallback:
                    out[t.id] = fallback
        return out

    def _base(self, t: AgentThread) -> dict:
        return {
            "id": t.id,
            "contact_email": t.contact_email,
            "subject": t.subject,
            "matched_customer_id": t.matched_customer_id,
            "status": t.status,
            "urgency": t.urgency,
            "category": t.category,
            "message_count": t.message_count,
            "last_message_at": self._iso(t.last_message_at),
            "last_direction": t.last_direction,
            "last_snippet": t.last_snippet,
            "has_pending": t.has_pending,
            "has_open_actions": t.has_open_actions,
            "assigned_to_user_id": t.assigned_to_user_id,
            "assigned_to_name": t.assigned_to_name,
            "assigned_at": self._iso(t.assigned_at),
            "visibility_permission": t.visibility_permission,
            "delivered_to": t.delivered_to,
            "case_id": t.case_id if hasattr(t, "case_id") else None,
            "case_number": (t.case.case_number if getattr(t, "case", None) else None),
            "case_title": (t.case.title if getattr(t, "case", None) else None),
            "folder_id": t.folder_id,
            # Phase 3 — AI summary cache. Null for short threads, orgs
            # without inbox_v2, and threads below the confidence floor.
            # Frontend falls back to last_snippet when null.
            "ai_summary_payload": t.ai_summary_payload if hasattr(t, "ai_summary_payload") else None,
            "is_historical": bool(getattr(t, "is_historical", False)),
        }
