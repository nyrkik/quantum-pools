"""Main flow that ties agents together."""

from src.core.ai_models import get_model
import os
import re
import logging
from datetime import datetime, timezone, timedelta

import anthropic
from sqlalchemy import select, desc, func
from src.core.database import get_db_context
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction
from src.models.customer import Customer

from .mail_agent import decode_email_header, extract_text_body
from .classifier import classify_and_draft, ANTHROPIC_KEY
from .communicator import send_email_response, FROM_EMAIL, FROM_NAME
from .customer_matcher import match_customer
from .thread_manager import get_or_create_thread, update_thread_status, _get_thread_open_actions

logger = logging.getLogger(__name__)

# Reply loop detection patterns
LOOP_PATTERNS = ["noreply@", "no-reply@", "mailer-daemon@", "postmaster@"]

# Block / route / tag / mark-as-read rules live in `inbox_rules`.
# See docs/inbox-rules-unification-plan.md for the unified schema.

# Internal team addresses — skip (handled by sent folder tracking)
INTERNAL_PATTERNS = ["sapphire-pools.com", "sapphire_pools", "quantumpoolspro.com"]


# Gratitude patterns removed — AI triage handles all edge cases now


def _msg_has_attachments(msg) -> bool:
    """True if the inbound email carries any file attachments.

    Uses walk() to handle both legacy email.message.Message (Gmail raw
    bytes path) and modern EmailMessage (webhook path). Detects any part
    whose Content-Disposition declares an attachment.
    """
    walk = getattr(msg, "walk", None)
    if walk is None:
        return False
    try:
        for part in walk():
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                return True
    except Exception:
        return False
    return False


def _msg_has_cc(msg) -> bool:
    """True if the inbound email has a Cc header with any content."""
    try:
        cc = msg.get("Cc", "") or msg.get("cc", "")
        return bool(cc and str(cc).strip())
    except Exception:
        return False


async def _queue_summary_if_inbox_v2(db, thread, organization_id: str) -> None:
    """If the org is on inbox v2, mark this thread to be summarized by
    the InboxSummarizerService on the next APScheduler sweep.

    Uses a 30-second debounce: if three quick inbounds land on the same
    thread within 30s, they all just push the debounce time forward —
    one summary regen per burst.

    No-op when the flag is off (org pays no Claude costs).
    """
    from datetime import datetime, timedelta, timezone
    from src.models.organization import Organization

    org = await db.get(Organization, organization_id)
    if not org or not getattr(org, "inbox_v2_enabled", False):
        return

    # Re-debounce every time an inbound arrives.
    thread.ai_summary_debounce_until = datetime.now(timezone.utc) + timedelta(seconds=30)
    await db.flush()


async def _emit_agent_message_received(
    db, agent_msg, msg=None, body_normalize_flags: dict | None = None,
):
    """Emit `agent_message.received` for a newly-created inbound AgentMessage.

    Called from each of the 3 AgentMessage-creation branches in
    process_incoming_email. Must be invoked AFTER db.flush() so agent_msg.id
    is populated, and BEFORE db.commit() so the event shares the txn.

    Actor is system — inbound emails don't have a user actor. Event is a
    system_action (the backend processed an incoming webhook).

    Optional `msg` is the underlying email.message object used to derive
    attachment/cc flags. Pass None if those signals aren't available.

    When ``body_normalize_flags`` contains at least one ``True`` flag the
    function also emits ``email.body_normalized`` — telemetry that lets us
    see which senders' bodies needed repair and how often, so the next
    Yardi-class quirk shows up in platform_events before a user asks.
    """
    from src.services.events.platform_event_service import PlatformEventService
    from src.services.events.actor_factory import actor_system

    provider = "gmail" if (agent_msg.email_uid or "").startswith("gmail-") else "webhook"
    refs = {
        "thread_id": agent_msg.thread_id,
        "agent_message_id": agent_msg.id,
    }
    if agent_msg.matched_customer_id:
        refs["customer_id"] = agent_msg.matched_customer_id
    await PlatformEventService.emit(
        db=db,
        event_type="agent_message.received",
        level="system_action",
        actor=actor_system(),
        organization_id=agent_msg.organization_id,
        entity_refs=refs,
        payload={
            "provider": provider,
            "had_attachments": _msg_has_attachments(msg) if msg is not None else False,
            "has_cc": _msg_has_cc(msg) if msg is not None else False,
        },
    )

    if body_normalize_flags and any(body_normalize_flags.values()):
        # `from_email_domain` not `from_email` — R2 bans any shape that
        # looks like a PII identifier (and the domain is what matters
        # for pattern-spotting anyway).
        domain = ""
        fe = (agent_msg.from_email or "").strip()
        if "@" in fe:
            domain = fe.rsplit("@", 1)[-1].lower()
        await PlatformEventService.emit(
            db=db,
            event_type="email.body_normalized",
            level="system_action",
            actor=actor_system(),
            organization_id=agent_msg.organization_id,
            entity_refs={
                "thread_id": agent_msg.thread_id,
                "agent_message_id": agent_msg.id,
            },
            payload={
                "provider": provider,
                "from_email_domain": domain,
                # Only include flags that actually fired — keeps payload
                # compact and lets the consumer filter by key presence.
                **{k: True for k, v in body_normalize_flags.items() if v},
            },
        )


async def _emit_agent_message_classified(db, agent_msg, classification_confidence: str | None = None):
    """Emit `agent_message.classified` after AI classification runs.

    Called after AgentMessage is persisted with category + urgency set by
    the classifier. Actor is agent (email_classifier). Safe to call for
    messages with no category — we skip emission in that case.
    """
    from src.services.events.platform_event_service import PlatformEventService
    from src.services.events.actor_factory import actor_agent

    if not agent_msg.category:
        return  # Not classified — nothing to record.

    await PlatformEventService.emit(
        db=db,
        event_type="agent_message.classified",
        level="agent_action",
        actor=actor_agent("email_classifier"),
        organization_id=agent_msg.organization_id,
        entity_refs={
            "thread_id": agent_msg.thread_id,
            "agent_message_id": agent_msg.id,
        },
        payload={
            "category": agent_msg.category,
            "urgency": agent_msg.urgency,
            "confidence": classification_confidence,
        },
    )


async def _mark_thread_auto_handled(
    thread_id: str,
    organization_id: str,
    category: str | None,
    matched_customer_id: str | None,
    classifier_confidence: str | None,
):
    """Stamp `thread.auto_handled_at` and emit `thread.auto_handled`.

    Called from each orchestrator auto-close path. The timestamp drives
    the AI Review folder query and the row-level "AI" pill; the event
    feeds the platform-events pipeline. Idempotent — won't overwrite a
    prior stamp if the thread is auto-closed twice (replay safe).
    """
    from src.services.events.platform_event_service import PlatformEventService
    from src.services.events.actor_factory import actor_agent

    async with get_db_context() as db:
        t = (await db.execute(
            select(AgentThread).where(AgentThread.id == thread_id)
        )).scalar_one_or_none()
        if not t:
            return
        if t.auto_handled_at is None:
            t.auto_handled_at = datetime.now(timezone.utc)

        refs: dict = {"thread_id": thread_id}
        if matched_customer_id:
            refs["customer_id"] = matched_customer_id
        try:
            await PlatformEventService.emit(
                db=db,
                event_type="thread.auto_handled",
                level="agent_action",
                actor=actor_agent("email_classifier"),
                organization_id=organization_id,
                entity_refs=refs,
                payload={
                    "category": category,
                    "classifier_confidence": classifier_confidence,
                },
            )
        except Exception as e:
            logger.warning(f"thread.auto_handled emit failed for {thread_id}: {e}")

        await db.commit()


async def _emit_agent_message_customer_matched(db, agent_msg, match_method: str | None):
    """Emit `agent_message.customer_matched` when a customer was matched.

    Skipped when no match was made. Actor is the customer_matcher agent.
    """
    from src.services.events.platform_event_service import PlatformEventService
    from src.services.events.actor_factory import actor_agent

    if not agent_msg.matched_customer_id:
        return  # No match to record.

    await PlatformEventService.emit(
        db=db,
        event_type="agent_message.customer_matched",
        level="agent_action",
        actor=actor_agent("customer_matcher"),
        organization_id=agent_msg.organization_id,
        entity_refs={
            "thread_id": agent_msg.thread_id,
            "agent_message_id": agent_msg.id,
            "customer_id": agent_msg.matched_customer_id,
        },
        payload={
            "method": match_method,
        },
    )


async def _persist_inbound_attachments(db, msg, agent_message_id: str, organization_id: str) -> None:
    """Walk an email.message.EmailMessage and persist any attachments as
    MessageAttachment rows + files on disk.

    Stores files at uploads/attachments/{org_id}/<uuid.ext> to match the same
    layout outbound attachments use, so the URL the inbox builds resolves.
    """
    if not msg or not organization_id:
        return
    import uuid as _uuid
    from pathlib import Path
    from src.core.config import settings
    from src.models.message_attachment import MessageAttachment

    upload_root = Path(settings.upload_dir) / "attachments" / organization_id
    upload_root.mkdir(parents=True, exist_ok=True)

    # Use walk() so we work with both legacy email.message.Message (returned
    # by email.message_from_bytes for Gmail raw) and the modern EmailMessage
    # (returned by stdlib EmailMessage() for webhook payloads).
    walk = getattr(msg, "walk", None)
    if walk is None:
        return
    for part in walk():
        try:
            if part.is_multipart():
                continue
            disposition = (part.get_content_disposition() or "").lower()
            filename = part.get_filename()
            # Treat anything explicitly attached, OR any inline part with a
            # filename and a non-text content type, as an attachment worth saving.
            mime_type = (part.get_content_type() or "application/octet-stream").lower()
            is_text_body = mime_type in ("text/plain", "text/html") and not filename
            if disposition not in ("attachment", "inline") and is_text_body:
                continue
            if disposition not in ("attachment", "inline") and not filename:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            filename = filename or f"attachment{Path(mime_type.replace('/', '.')).suffix or ''}"
            ext = Path(filename).suffix
            stored_filename = f"{_uuid.uuid4().hex}{ext}"
            (upload_root / stored_filename).write_bytes(payload)

            db.add(MessageAttachment(
                organization_id=organization_id,
                source_type="agent_message",
                source_id=agent_message_id,
                filename=filename[:255],
                stored_filename=stored_filename,
                mime_type=mime_type[:100],
                file_size=len(payload),
            ))
        except Exception as e:
            logger.warning(f"Skipping unparseable attachment on message {agent_message_id}: {e}")


def _is_own_email(from_email: str) -> bool:
    """Check if the email is from one of our own addresses (reply loop prevention)."""
    addr = from_email.lower().strip()
    # Check our own sending addresses
    if FROM_EMAIL and addr == FROM_EMAIL.lower():
        return True
    gmail_user = os.environ.get("AGENT_GMAIL_USER", "")
    if gmail_user and addr == gmail_user.lower():
        return True
    # Check common no-reply patterns
    for pattern in LOOP_PATTERNS:
        if pattern in addr:
            return True
    return False


def _extract_delivered_to(msg) -> str | None:
    """Extract the recipient address from an inbound email.

    Prefers the RFC Delivered-To header (Gmail aliases, Postmark includes
    it), falling back to the first parseable address in the To header.
    """
    import re as _re

    delivered_to = msg.get("Delivered-To", "")
    if delivered_to:
        delivered_to = decode_email_header(delivered_to).strip()
        match = _re.search(r"<(.+?)>", delivered_to)
        if match:
            return match.group(1).lower()
        if "@" in delivered_to:
            return delivered_to.lower()

    to_header = decode_email_header(msg.get("To", ""))
    if to_header:
        addresses = _re.findall(r"[\w.+-]+@[\w.-]+", to_header)
        for addr in addresses:
            return addr.lower()
    return None


async def process_incoming_email(
    uid: str,
    msg,
    organization_id: str = "",
    historical: bool = False,
    gmail_labels: list[str] | None = None,
):
    """Process a single incoming email.

    ``gmail_labels`` is the Gmail API's labelIds array for the source message
    when the email came from a Gmail API sync. When "SPAM" is present we
    trust Gmail's judgment and skip the AI classifier — the known-customer
    override below still fires so flagged customer mail is routed for human
    review instead of being silently hidden.
    """
    gmail_labels = gmail_labels or []
    gmail_flagged_spam = "SPAM" in gmail_labels
    from_header = decode_email_header(msg.get("From", ""))
    subject = decode_email_header(msg.get("Subject", ""))
    from src.services.agents.mail_agent import (
        consume_last_body_normalize_flags,
        extract_bodies,
    )
    body, body_html = extract_bodies(msg)
    # Capture right after extract_bodies — the ContextVar holds the
    # flags until we read or clear them. Passed into
    # `_emit_agent_message_received` so `email.body_normalized` can
    # attach itself to a real agent_message_id.
    body_normalize_flags = consume_last_body_normalize_flags()
    # Safety net: if body still looks like raw HTML, strip it now
    if body and "<html" in body.lower()[:200]:
        from src.services.agents.mail_agent import _clean_html
        body = _clean_html(body)
        body_normalize_flags["html_stripped_from_text"] = True
    message_id_header = msg.get("Message-ID", "")

    # Parse actual email date
    from email.utils import parsedate_to_datetime
    email_date = None
    try:
        date_header = msg.get("Date", "")
        if date_header:
            email_date = parsedate_to_datetime(date_header)
            if email_date.tzinfo is None:
                email_date = email_date.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    if not email_date:
        email_date = datetime.now(timezone.utc)

    # Extract email address + display name from From header via the
    # RFC 5322-compliant parser. Falls back to regex on malformed
    # headers — never raises.
    from src.services.agents.mail_agent import parse_from_header
    from_name_parsed, from_email_parsed = parse_from_header(from_header)
    from_email = from_email_parsed or from_header
    from_name = from_name_parsed or None

    to_header = decode_email_header(msg.get("To", ""))

    # --- Extract Delivered-To for routing ---
    delivered_to_addr = _extract_delivered_to(msg)

    # --- Reply loop prevention ---
    if _is_own_email(from_email):
        logger.info(f"Skipping own email: {from_email}: {subject}")
        return

    from_lower = from_email.lower()

    # --- Skip internal team emails ---
    if any(p in from_lower for p in INTERNAL_PATTERNS):
        logger.info(f"Skipping internal email: {from_email}: {subject}")
        return

    # Block rules (route_to_spam) are now evaluated in the folder-assign
    # block below via InboxRulesService.evaluate(). `block_rule` is kept
    # as a compatibility flag so legacy callers of update_thread_status
    # still behave — but its value is derived down there, not here.
    block_rule = False

    logger.info(f"Processing email from {from_email}: {(subject or '')[:60]}")

    # Check if already processed — by email_uid OR RFC Message-ID (cross-source dedup)
    async with get_db_context() as db:
        existing = await db.execute(
            select(AgentMessage).where(AgentMessage.email_uid == uid)
        )
        if existing.scalar_one_or_none():
            logger.info(f"Already processed (uid): {uid}")
            return
        if message_id_header:
            existing_rfc = await db.execute(
                select(AgentMessage).where(AgentMessage.rfc_message_id == message_id_header).limit(1)
            )
            if existing_rfc.scalar_one_or_none():
                logger.info(f"Already processed (rfc_message_id): {message_id_header}")
                return

    # --- Thread: get or create (with routing rule matching) ---
    # Pre-evaluate inbox_rules on the recipient address so the new thread
    # is born with the right visibility + category. The post-ingest folder-
    # assign block (below) re-runs the full evaluation against the final
    # thread state and applies folder/tag/mark-as-read actions.
    routing_kwargs: dict = {}
    if delivered_to_addr and organization_id:
        from src.services.inbox_rules_service import (
            ACTION_ASSIGN_CATEGORY,
            ACTION_SET_VISIBILITY,
            InboxRulesService,
            build_context,
        )
        async with get_db_context() as db:
            actions = await InboxRulesService(db).evaluate(
                build_context(
                    sender_email=from_email,
                    recipient_email=delivered_to_addr,
                    subject=subject,
                ),
                organization_id,
            )
        for action in actions:
            atype = action.get("type")
            params = action.get("params") or {}
            if atype == ACTION_SET_VISIBILITY:
                role_slugs = params.get("role_slugs") or []
                if role_slugs:
                    routing_kwargs["visibility_role_slugs"] = list(role_slugs)
            elif atype == ACTION_ASSIGN_CATEGORY:
                cat = params.get("category")
                if cat:
                    routing_kwargs["category"] = cat
        routing_kwargs["delivered_to"] = delivered_to_addr

    thread = await get_or_create_thread(from_email, subject, organization_id=organization_id, **routing_kwargs)
    thread_context = ""
    existing_action_descriptions = []

    # Build thread context from existing messages
    if thread.message_count > 0:
        async with get_db_context() as db:
            prev_msgs = (await db.execute(
                select(AgentMessage)
                .where(AgentMessage.thread_id == thread.id)
                .order_by(desc(AgentMessage.received_at))
                .limit(5)
            )).scalars().all()

            if prev_msgs:
                logger.info(f"Thread {thread.id[:8]}: {thread.message_count} existing messages")
                thread_context = "\n\n=== THIS IS A FOLLOW-UP IN AN EXISTING THREAD ==="
                for pm in reversed(prev_msgs):
                    direction = "Client" if pm.direction == "inbound" else "Us"
                    thread_context += f"\n[{direction}] {pm.subject}: {(pm.body or '')[:200]}"
                    if pm.final_response and pm.direction == "inbound":
                        thread_context += f"\n[Us] Reply: {pm.final_response[:200]}"
                thread_context += "\nDo NOT create duplicate action items. Only add new actions if this email introduces genuinely new work."
                existing_action_descriptions = await _get_thread_open_actions(thread.id)

    # --- Pre-check: is this sender a known customer? ---
    # If yes, NEVER auto-ignore — always require human review.
    sender_is_customer = bool(thread and thread.matched_customer_id)
    # Defined at the function scope so the downstream proposal-staging
    # block can reference it whether or not the pre-match branch ran
    # (known-customer threads skip the matcher + its unverified_sink).
    # Regression: `tests/test_orchestrator_known_customer_scoping.py`.
    unverified_candidates: list[dict] = []
    if not sender_is_customer:
        # Honor `skip_customer_match` inbox-rule advisory: for shared /
        # regional senders we don't want to reuse the last thread's match,
        # because this email may be about a different customer than the
        # previous one. The matcher's step 2 is the risky shortcut.
        skip_prev = False
        if organization_id:
            try:
                from src.services.inbox_rules_service import (
                    ACTION_SKIP_CUSTOMER_MATCH,
                    InboxRulesService,
                    build_context,
                )
                async with get_db_context() as db:
                    shared_actions = await InboxRulesService(db).evaluate(
                        build_context(sender_email=from_email),
                        organization_id,
                    )
                skip_prev = any(
                    a.get("type") == ACTION_SKIP_CUSTOMER_MATCH
                    for a in shared_actions
                )
            except Exception as e:
                logger.warning(f"skip_customer_match check failed: {e}")

        # Quick check: does this email match a customer directly?
        # Phase 5: collect any fuzzy candidates the QC verifier dropped so
        # we can surface them to a human via customer_match_suggestion
        # proposals after the agent_msg is persisted. The list itself is
        # declared above at function scope; `match_customer` only mutates.
        pre_match = await match_customer(
            from_email, subject, body[:500], from_header,
            skip_previous_match=skip_prev,
            unverified_sink=unverified_candidates,
            organization_id=organization_id or None,
        )
        if pre_match and pre_match.get("customer_id"):
            sender_is_customer = True
            # Update thread with customer info now so it's available downstream
            if thread:
                async with get_db_context() as db:
                    t = (await db.execute(select(AgentThread).where(AgentThread.id == thread.id))).scalar_one_or_none()
                    if t and not t.matched_customer_id:
                        t.matched_customer_id = pre_match["customer_id"]
                        t.customer_name = pre_match.get("customer_name")
                        t.property_address = pre_match.get("property_address")
                        await db.commit()

    # --- AI triage: does this email need a response? ---
    from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature
    clean_body = strip_email_signature(strip_quoted_reply(body)) if body else ""

    from .triage_agent import ai_triage
    needs_response = await ai_triage(
        clean_body, subject, from_email,
        organization_id=organization_id or None,
    )
    if not needs_response:
        logger.info(f"AI triage: no response needed — {subject[:50]}")
        if sender_is_customer:
            logger.info(f"  ...but sender is a customer — proceeding with classification")

    # Classify and draft — Gmail-flagged spam skips the AI classifier entirely.
    # The downstream "spam + known customer" override (below) still forces
    # human review if Gmail flags a customer we recognize.
    if gmail_flagged_spam:
        logger.info(f"Gmail-labeled SPAM, bypassing classifier: {(subject or '')[:60]}")
        result = {
            "category": "spam",
            "needs_approval": False,
            "draft_response": "",
            "confidence": "high",
        }
    else:
        result = await classify_and_draft(from_email, subject, body + thread_context, from_header=from_header)

    category = result.get("category", "general")

    # Safety net: known billing/payment senders must never be classified as auto_reply.
    # They look like auto-replies (bounce domains, no-reply) but contain critical financial info.
    BILLING_SENDER_PATTERNS = (
        "stripe.com", "bounce.stripe.com",
        "paypal.com", "intuit.com", "quickbooks.com",
        "bill.com", "square.com", "squareup.com",
        "appfolio.com", "entrata.com", "coupahost.com",
        "venmo.com", "wave.com",
    )
    sender_lower = from_email.lower()
    if category == "auto_reply" and any(p in sender_lower for p in BILLING_SENDER_PATTERNS):
        logger.info(f"Override: {from_email} is billing sender, not auto_reply — reclassifying as billing")
        category = "billing"
        result["category"] = "billing"
        result["needs_approval"] = False  # info-only, but visible in inbox

    # Auto-handle general + no draft: the AI couldn't classify it specifically
    # AND couldn't draft a response — it's informational (payment notifications,
    # marketing, system alerts). Don't waste a human's time on it.
    draft = result.get("draft_response", "")
    if category == "general" and not draft and not sender_is_customer:
        logger.info(f"Auto-handled general (no draft, not customer): {subject[:50]}")
        async with get_db_context() as db:
            agent_msg = AgentMessage(
                organization_id=organization_id,
                email_uid=uid,
                rfc_message_id=message_id_header or None,
                direction="inbound",
                from_email=from_email,
                from_name=from_name,
                to_email=to_header,
                subject=subject,
                body=body[:5000],
                body_html=body_html[:50000] if body_html else None,
                category=category,
                urgency="low",
                status="handled",
                customer_name=result.get("customer_name"),
                received_at=email_date,
                thread_id=thread.id,
                delivered_to=delivered_to_addr,
            )
            db.add(agent_msg)
            await db.flush()
            await _emit_agent_message_received(db, agent_msg, msg=msg, body_normalize_flags=body_normalize_flags)
            await _emit_agent_message_classified(db, agent_msg, classification_confidence=result.get("confidence"))
            await _emit_agent_message_customer_matched(db, agent_msg, match_method=result.get("_match_method"))
            await db.commit()
        await update_thread_status(thread.id)
        await _mark_thread_auto_handled(
            thread.id, organization_id, category,
            result.get("_matched_customer_id"), result.get("confidence"),
        )
        return

    if category in ("spam", "auto_reply", "no_response", "thank_you"):
        # First-contact guardrail: if the sender isn't a matched customer AND
        # we've never seen this sender before in this org, don't silently
        # auto-handle — keep it pending so a human reviews. Protects against
        # the "I sent a test to accounting@ and it vanished" failure mode
        # where the classifier mislabels a first-touch as no_response.
        is_first_contact_unknown = False
        if not sender_is_customer and category in ("no_response", "thank_you"):
            async with get_db_context() as _fc_db:
                prior = (await _fc_db.execute(
                    select(AgentMessage.id).where(
                        AgentMessage.organization_id == organization_id,
                        AgentMessage.from_email == from_email,
                        AgentMessage.direction == "inbound",
                    ).limit(1)
                )).scalar_one_or_none()
            is_first_contact_unknown = prior is None

        if sender_is_customer and category in ("spam", "auto_reply"):
            # Spam/auto-reply from a customer address is suspicious — override to pending
            logger.info(f"Customer email classified as {category}, overriding to pending: {subject[:50]}")
            category = "general"
            result["category"] = "general"
            result["needs_approval"] = True
        elif category not in ("spam", "auto_reply") and sender_is_customer and result.get("confidence") != "high":
            # Low/medium confidence no_response from a customer — play it safe
            logger.info(f"Customer email classified as {category} (confidence={result.get('confidence')}), overriding to pending: {subject[:50]}")
            category = "general"
            result["category"] = "general"
            result["needs_approval"] = True
        elif is_first_contact_unknown:
            logger.info(
                f"First-contact unknown classified as {category}, overriding to pending: "
                f"from={from_email} subj={subject[:50]}"
            )
            category = "general"
            result["category"] = "general"
            result["needs_approval"] = True
        else:
            logger.info(f"Auto-handled {category}: {(subject or '')[:60]}")
            async with get_db_context() as db:
                agent_msg = AgentMessage(
                    organization_id=organization_id,
                    email_uid=uid,
                    rfc_message_id=message_id_header or None,
                    direction="inbound",
                    from_email=from_email,
                    from_name=from_name,
                    to_email=to_header,
                    subject=subject,
                    body=body[:5000],
                    body_html=body_html[:50000] if body_html else None,
                    category=category,
                    urgency="low",
                    status="handled",
                    customer_name=result.get("customer_name"),
                    received_at=email_date,
                    thread_id=thread.id,
                    delivered_to=delivered_to_addr,
                )
                db.add(agent_msg)
                await db.flush()
                await _emit_agent_message_received(db, agent_msg, msg=msg, body_normalize_flags=body_normalize_flags)
                await _emit_agent_message_classified(db, agent_msg, classification_confidence=result.get("confidence"))
                await _emit_agent_message_customer_matched(db, agent_msg, match_method=result.get("_match_method"))
                await db.commit()

                # Route spam + auto_reply to the Spam system folder unless the
                # user has manually moved this thread. Without this, auto-
                # handled spam stays in whatever folder the thread was born in
                # (usually NULL = Inbox) and never surfaces in Spam either,
                # since the Spam folder view filters by folder_id.
                if category in ("spam", "auto_reply") and organization_id:
                    try:
                        from src.services.inbox_folder_service import InboxFolderService
                        t = (await db.execute(
                            select(AgentThread).where(AgentThread.id == thread.id)
                        )).scalar_one_or_none()
                        if t and not t.folder_override:
                            spam_folder_id = await InboxFolderService(db).get_system_folder_id(
                                organization_id, "spam"
                            )
                            if spam_folder_id and t.folder_id != spam_folder_id:
                                t.folder_id = spam_folder_id
                                await db.commit()
                    except Exception as e:
                        logger.warning(f"Spam folder assign failed for thread {thread.id}: {e}")
            await update_thread_status(thread.id)
            await _mark_thread_auto_handled(
                thread.id, organization_id, category,
                result.get("_matched_customer_id"), result.get("confidence"),
            )
            return

    # Save to DB
    async with get_db_context() as db:
        # Update thread with customer info from classification
        thread_obj = (await db.execute(select(AgentThread).where(AgentThread.id == thread.id))).scalar_one_or_none()
        if thread_obj:
            if result.get("_matched_customer_id") and not thread_obj.matched_customer_id:
                thread_obj.matched_customer_id = result["_matched_customer_id"]
            if result.get("customer_name") and not thread_obj.customer_name:
                thread_obj.customer_name = result["customer_name"]
            if result.get("_property_address") and not thread_obj.property_address:
                thread_obj.property_address = result["_property_address"]

        # Inherit case_id from thread if it already has one (don't create cases from emails)
        case_id = thread_obj.case_id if thread_obj else None

        # Phase 5 Step 5 closeout (2026-04-24): classifier drafts are ALWAYS
        # staged as email_reply proposals — the inbox reading pane renders
        # ProposalCard exclusively. DNA rule 5: AI never commits to customer.
        classifier_draft = result.get("draft_response")

        agent_msg = AgentMessage(
            organization_id=organization_id,
            email_uid=uid,
            rfc_message_id=message_id_header or None,
            direction="inbound",
            from_email=from_email,
            from_name=from_name,
            to_email=to_header,
            subject=subject,
            body=body[:5000],
            category=category,
            urgency=result.get("urgency", "medium"),
            status="pending",
            received_at=email_date,
            matched_customer_id=result.get("_matched_customer_id"),
            match_method=result.get("_match_method"),
            customer_name=result.get("customer_name"),
            property_address=result.get("_property_address"),
            notes=result.get("internal_note"),
            thread_id=thread.id,
            delivered_to=delivered_to_addr,
        )
        db.add(agent_msg)
        await db.flush()

        if classifier_draft:
            try:
                from src.services.events.actor_factory import actor_agent
                from src.services.proposals import ProposalService
                reply_subject = (
                    subject if subject and subject.startswith("Re:")
                    else (f"Re: {subject}" if subject else "")
                )
                await ProposalService(db).stage(
                    org_id=organization_id,
                    agent_type="email_drafter",
                    entity_type="email_reply",
                    source_type="message",
                    source_id=agent_msg.id,
                    proposed_payload={
                        "thread_id": thread.id,
                        "reply_to_message_id": agent_msg.id,
                        "to": from_email,
                        "subject": reply_subject,
                        "body": classifier_draft,
                        "customer_id": result.get("_matched_customer_id"),
                    },
                    confidence=result.get("confidence") if isinstance(result.get("confidence"), (int, float)) else None,
                    input_context=(body[:500] if body else None),
                    actor=actor_agent("email_drafter"),
                )
            except Exception as e:
                # Never break ingest on proposal-stage failure; user can
                # reply manually from the thread sheet's inline composer.
                logger.warning(f"email_reply proposal stage failed for msg {agent_msg.id}: {e}")

        # Low-confidence customer-match candidates dropped by the QC verifier
        # become review proposals at /inbox/matches (owner+admin).
        if unverified_candidates:
            for candidate in unverified_candidates:
                try:
                    from src.services.events.actor_factory import actor_agent
                    from src.services.proposals import ProposalService
                    await ProposalService(db).stage(
                        org_id=organization_id,
                        agent_type="customer_matcher",
                        entity_type="customer_match_suggestion",
                        source_type="thread",
                        source_id=thread.id,
                        proposed_payload={
                            "thread_id": thread.id,
                            "candidate_customer_id": candidate["candidate_customer_id"],
                            "reason": candidate["reason"],
                            "confidence": "medium",
                        },
                        input_context=f"Sender: {from_email}; subject: {subject[:120] if subject else ''}",
                        actor=actor_agent("customer_matcher"),
                    )
                except Exception as e:
                    logger.warning(
                        f"customer_match_suggestion stage failed for thread {thread.id}: {e}"
                    )

        await _emit_agent_message_received(db, agent_msg, msg=msg, body_normalize_flags=body_normalize_flags)
        await _emit_agent_message_classified(db, agent_msg, classification_confidence=result.get("confidence"))
        await _emit_agent_message_customer_matched(db, agent_msg, match_method=result.get("_match_method"))

        # Phase 3 — queue a summary regeneration for this thread if the
        # org is on inbox v2. 30-second debounce coalesces reply bursts.
        # Actual regen runs via APScheduler sweep (app.py job).
        try:
            await _queue_summary_if_inbox_v2(db, thread, organization_id)
        except Exception as e:
            logger.warning(f"inbox-v2 summary queue failed for thread {thread.id}: {e}")

        # Persist any inbound attachments as MessageAttachment rows so the inbox
        # reading pane can render images/docs the customer sent us.
        try:
            await _persist_inbound_attachments(db, msg, agent_msg.id, organization_id)
        except Exception as e:
            logger.warning(f"Failed to persist attachments for {uid}: {e}")

        # Historical sync: ingest + classify + thread, but no outbound actions
        if historical:
            agent_msg.status = "handled"
            agent_msg.notes = (agent_msg.notes or "") + "\nHistorical sync — no actions or replies generated."
            agent_msg.notes = agent_msg.notes.strip()
            await db.commit()
            await update_thread_status(thread.id)
            return

        # Create action items — skip duplicates
        # Check both thread-level and org-wide open actions for same customer/property
        all_open_descriptions = list(existing_action_descriptions)  # thread-level
        if result.get("customer_name") or result.get("_property_address"):
            # Also check org-wide open actions for same customer/property
            org_open_query = select(AgentAction.description, AgentAction.action_type).where(
                AgentAction.organization_id == organization_id,
                AgentAction.status.in_(("open", "in_progress")),
            )
            if result.get("customer_name"):
                org_open_query = org_open_query.where(
                    AgentAction.customer_name == result.get("customer_name")
                )
            org_open = (await db.execute(org_open_query)).all()
            for open_desc, atype in org_open:
                if open_desc not in all_open_descriptions:
                    all_open_descriptions.append(open_desc)

        actions = result.get("actions", [])[:3]  # Hard cap: max 3 actions per email
        for action in actions:
            if not action.get("description"):
                continue
            # Skip if similar action already exists (thread or org-wide)
            desc_lower = action["description"].lower()
            action_type = action.get("action_type", "other")
            is_duplicate = False
            for existing_desc in all_open_descriptions:
                existing_words = set(existing_desc.lower().split())
                new_words = set(desc_lower.split())
                if existing_words and new_words:
                    # Word overlap check
                    overlap = len(existing_words & new_words) / max(len(existing_words), len(new_words))
                    if overlap > 0.5:  # Lowered from 0.6 to catch more duplicates
                        is_duplicate = True
                        logger.info(f"Skipping duplicate action (word overlap {overlap:.0%}): {action['description'][:60]}")
                        break
                    # Same address + same action type = likely duplicate
                    if result.get("_property_address"):
                        addr = result["_property_address"].lower()
                        if addr[:20] in existing_desc.lower() and action_type in existing_desc.lower():
                            is_duplicate = True
                            logger.info(f"Skipping duplicate action (same address+type): {action['description'][:60]}")
                            break
            if is_duplicate:
                continue

            due_days = action.get("due_days", 3)
            due_date = datetime.now(timezone.utc) + timedelta(days=due_days) if due_days else None
            # Resolve customer_id: thread match > classification result
            cust_id = (thread_obj.matched_customer_id if thread_obj else None) or result.get("_matched_customer_id")
            cust_name = (thread_obj.customer_name if thread_obj else None) or result.get("customer_name")
            prop_addr = (thread_obj.property_address if thread_obj else None) or result.get("_property_address")

            # Cases are created manually by users from the inbox (Create Case / Create Job buttons).
            # Auto-creating cases from every email action clutters the case list with noise.

            from src.services.agent_action_service import AgentActionService
            from src.services.events.actor_factory import actor_agent
            await AgentActionService(db).add_job(
                org_id=organization_id,
                action_type=action.get("action_type", "other"),
                description=action["description"][:80],
                source="thread_ai",
                actor=actor_agent("email_classifier"),
                case_id=case_id,
                thread_id=thread.id,
                agent_message_id=agent_msg.id,
                customer_id=cust_id,
                customer_name=cust_name,
                property_address=prop_addr,
                due_date=due_date,
                created_by="DeepBlue",
            )

        await db.commit()

        # Auto-send removed 2026-04-14 — all AI-drafted replies now require
        # human approval via ProposalCard in the inbox reading pane (Phase 5
        # Steps 4+5). The SMS urgency-ping path that used to fan out here was
        # retired 2026-04-24 — its reply-to-approve counterpart was already
        # dead code, and the Twilio number had drifted off our account. ntfy
        # on MS-01:7031 is where future team-urgency pings should live.

    # Update thread status
    await update_thread_status(thread.id)

    # Auto-assign folder + apply rule-driven thread mutations (mark-as-read,
    # category, visibility) via InboxRulesService. User-moved threads
    # (folder_override=True) skip folder reassignment but still receive
    # mark-as-read so the read state stays accurate.
    try:
        async with get_db_context() as db:
            t = (await db.execute(select(AgentThread).where(AgentThread.id == thread.id))).scalar_one_or_none()
            if t:
                from src.services.inbox_folder_service import InboxFolderService
                from src.services.inbox_rules_service import (
                    ACTION_ASSIGN_FOLDER,
                    ACTION_ASSIGN_TAG,
                    ACTION_ROUTE_TO_SPAM,
                    ACTION_SUPPRESS_CONTACT_PROMPT,
                    InboxRulesService,
                    build_context,
                )
                svc = InboxFolderService(db)
                rules_svc = InboxRulesService(db)

                rule_actions = await rules_svc.evaluate(
                    build_context(
                        sender_email=t.contact_email,
                        recipient_email=t.delivered_to,
                        subject=t.subject,
                        category=t.category,
                        customer_id=t.matched_customer_id,
                    ),
                    organization_id,
                ) if organization_id else []

                # Apply non-folder rule actions (mark_as_read, assign_category,
                # set_visibility). Folder assignment is handled below so the
                # legacy "block/spam/sent" heuristics still take precedence.
                non_folder_actions = [
                    a for a in rule_actions
                    if a.get("type") not in {
                        ACTION_ASSIGN_FOLDER,
                        ACTION_ROUTE_TO_SPAM,
                        ACTION_ASSIGN_TAG,
                        ACTION_SUPPRESS_CONTACT_PROMPT,
                    }
                ]
                if non_folder_actions:
                    await rules_svc.apply(non_folder_actions, t)

                if not t.folder_override:
                    target_key = None
                    target_folder_id = None
                    if block_rule:
                        target_key = "spam"
                    elif t.category in ("spam", "auto_reply"):
                        target_key = "spam"
                    elif t.last_direction == "outbound" and not t.has_pending:
                        target_key = "sent"
                    else:
                        # Folder routing from the rule engine. route_to_spam
                        # short-circuits to the Spam system folder.
                        for action in rule_actions:
                            atype = action.get("type")
                            params = action.get("params") or {}
                            if atype == ACTION_ROUTE_TO_SPAM:
                                target_key = "spam"
                                break
                            if atype == ACTION_ASSIGN_FOLDER and params.get("folder_id"):
                                target_folder_id = params["folder_id"]
                                break
                    if target_key:
                        target_folder_id = await svc.get_system_folder_id(organization_id, target_key)
                    if target_folder_id and t.folder_id != target_folder_id:
                        t.folder_id = target_folder_id
                await db.commit()
    except Exception as e:
        logger.warning(f"Folder auto-assign failed for thread {thread.id}: {e}")

    # Push real-time event
    try:
        from src.core.events import EventType, publish
        is_new = thread.message_count <= 1
        await publish(
            EventType.THREAD_NEW if is_new else EventType.THREAD_MESSAGE_NEW,
            organization_id,
            {"thread_id": str(thread.id), "from_email": from_email, "subject": subject[:80]},
        )
    except Exception:
        pass  # Non-blocking — never break email processing

    # Post-processing: verify customer match integrity
    from .customer_matcher import verify_customer_match
    await verify_customer_match(organization_id, from_email, thread.id)


    # Extracted to customer_matcher.py — kept as import target for backward compat


async def save_discovered_contact(agent_msg_id: str):
    """Delegated to customer_matcher.save_discovered_contact."""
    from .customer_matcher import save_discovered_contact as _save
    await _save(agent_msg_id)


async def _get_default_org_id() -> str:
    """Get the first active org with agent enabled. Falls back to first org."""
    from src.models.organization import Organization
    async with get_db_context() as db:
        result = await db.execute(
            select(Organization).where(Organization.agent_enabled == True).order_by(Organization.created_at).limit(1)
        )
        org = result.scalar_one_or_none()
        if org:
            return org.id
        # Fallback
        result = await db.execute(select(Organization).order_by(Organization.created_at).limit(1))
        org = result.scalar_one_or_none()
        return org.id if org else ""


    # _ai_triage extracted to triage_agent.py
    # _process_sent_emails extracted to sent_tracker.py


async def auto_close_stale_visits():
    """Auto-close stale visits. Called from agent_poller on a schedule."""
    org_id = await _get_default_org_id()
    if not org_id:
        return
    from src.services.visit_experience_service import VisitExperienceService
    async with get_db_context() as db:
        svc = VisitExperienceService(db)
        closed = await svc.auto_close_stale_visits(org_id)
        if closed:
            logger.info(f"Auto-closed {closed} stale visit(s)")
        await db.commit()
