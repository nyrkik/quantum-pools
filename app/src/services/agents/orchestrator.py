"""Main flow that ties agents together."""

from src.core.ai_models import get_model
import os
import re
import logging
from datetime import datetime, timezone, timedelta

import anthropic
from sqlalchemy import select, desc
from src.core.database import get_db_context
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction
from src.models.customer import Customer

from .mail_agent import poll_inbox, mark_processed, decode_email_header, extract_text_body
from .classifier import classify_and_draft, ANTHROPIC_KEY
from .communicator import (
    send_email_response, send_approval_request, send_sms, notify_others,
    FROM_EMAIL, FROM_NAME, APPROVAL_NUMBERS,
)
from .customer_matcher import match_customer
from .thread_manager import get_or_create_thread, update_thread_status, _get_thread_open_actions

logger = logging.getLogger(__name__)

# Track pending approvals: message_id -> AgentMessage.id
_pending_approvals: dict[str, str] = {}

# Auto-close stale visits: only check every 30 minutes
_last_auto_close_check: datetime | None = None
AUTO_CLOSE_INTERVAL_MINUTES = 30

# Flood protection: track recent SMS alerts per sender
_recent_alerts: dict[str, datetime] = {}
ALERT_COOLDOWN_MINUTES = 10

# Business hours (Pacific time)
BUSINESS_HOUR_START = 7  # 7 AM
BUSINESS_HOUR_END = 20   # 8 PM

# Reply loop detection patterns
LOOP_PATTERNS = ["noreply@", "no-reply@", "mailer-daemon@", "postmaster@"]

# Block rules are now in DB (inbox_routing_rules with action='block', match_field='from').
# See migration seed for the full list of blocked sender domains/patterns.

# Internal team addresses — skip (handled by sent folder tracking)
INTERNAL_PATTERNS = ["sapphire-pools.com", "sapphire_pools", "quantumpoolspro.com"]


# Gratitude patterns removed — AI triage handles all edge cases now


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


def _is_business_hours() -> bool:
    """Check if current time is within business hours (Pacific)."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        return BUSINESS_HOUR_START <= now.hour < BUSINESS_HOUR_END and now.weekday() < 5
    except Exception:
        return True  # Default to allowing if timezone fails


def _should_throttle_alert(from_email: str) -> bool:
    """Check if we've already alerted about this sender recently."""
    addr = from_email.lower()
    now = datetime.now(timezone.utc)
    last = _recent_alerts.get(addr)
    if last and (now - last).total_seconds() < ALERT_COOLDOWN_MINUTES * 60:
        return True
    _recent_alerts[addr] = now
    # Clean old entries
    cutoff = now - timedelta(minutes=ALERT_COOLDOWN_MINUTES * 2)
    for k in list(_recent_alerts.keys()):
        if _recent_alerts[k] < cutoff:
            del _recent_alerts[k]
    return False


async def process_incoming_email(uid: str, msg, organization_id: str = ""):
    """Process a single incoming email."""
    from_header = decode_email_header(msg.get("From", ""))
    subject = decode_email_header(msg.get("Subject", ""))
    body = extract_text_body(msg)
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

    # Extract email address from From header
    email_match = re.search(r"<(.+?)>", from_header)
    from_email = email_match.group(1) if email_match else from_header

    to_header = decode_email_header(msg.get("To", ""))

    # --- Extract Delivered-To for routing ---
    from src.services.inbox_routing_service import extract_delivered_to
    delivered_to_addr = extract_delivered_to(msg)

    # --- Reply loop prevention ---
    if _is_own_email(from_email):
        logger.info(f"Skipping own email: {from_email}: {subject}")
        return

    from_lower = from_email.lower()

    # --- Skip internal team emails ---
    if any(p in from_lower for p in INTERNAL_PATTERNS):
        logger.info(f"Skipping internal email: {from_email}: {subject}")
        return

    # --- Check DB block rules (replaces hardcoded AUTO_SENDER_DOMAINS) ---
    if organization_id:
        from src.services.inbox_routing_service import check_sender_blocked
        async with get_db_context() as db:
            block_rule = await check_sender_blocked(db, organization_id, from_email)
        if block_rule:
            logger.info(f"Blocked by rule '{block_rule.address_pattern}': {from_email}: {subject}")
            return

    logger.info(f"Processing email from {from_email}: {subject}")

    # Check if already processed
    async with get_db_context() as db:
        existing = await db.execute(
            select(AgentMessage).where(AgentMessage.email_uid == uid)
        )
        if existing.scalar_one_or_none():
            logger.info(f"Already processed: {uid}")
            return

    # --- Thread: get or create (with routing rule matching) ---
    # Match routing rules to set visibility on new threads
    routing_kwargs: dict = {}
    if delivered_to_addr and organization_id:
        from src.services.inbox_routing_service import match_routing_rule
        async with get_db_context() as db:
            rule = await match_routing_rule(db, organization_id, delivered_to_addr)
        if rule:
            routing_kwargs["visibility_permission"] = rule.required_permission
            routing_kwargs["delivered_to"] = delivered_to_addr
            routing_kwargs["routing_rule_id"] = rule.id
            if rule.category:
                routing_kwargs["category"] = rule.category
            logger.info(f"Routing rule matched: {rule.address_pattern} -> perm={rule.required_permission}")
        else:
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

    # --- AI triage: does this email need a response? ---
    from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature
    clean_body = strip_email_signature(strip_quoted_reply(body)) if body else ""

    needs_response = await _ai_triage(clean_body, subject, from_email)
    if not needs_response:
        logger.info(f"AI triage: no response needed — {subject[:50]}")
        async with get_db_context() as db:
            agent_msg = AgentMessage(
                organization_id=organization_id,
                email_uid=uid,
                direction="inbound",
                from_email=from_email,
                to_email=to_header,
                subject=subject,
                body=body,
                status="handled",
                category="no_response",
                delivered_to=delivered_to_addr,
                thread_id=thread.id if thread else None,
                matched_customer_id=thread.matched_customer_id if thread else None,
                customer_name=thread.customer_name if thread else None,
            )
            db.add(agent_msg)
            if thread:
                thread_obj = (await db.execute(
                    select(AgentThread).where(AgentThread.id == thread.id)
                )).scalar_one_or_none()
                if thread_obj:
                    thread_obj.message_count = (thread_obj.message_count or 0) + 1
                    thread_obj.last_message_at = datetime.now(timezone.utc)
                    thread_obj.last_direction = "inbound"
                    thread_obj.last_snippet = (clean_body or "")[:200]
            await db.commit()
        return

    # Classify and draft
    result = await classify_and_draft(from_email, subject, body + thread_context, from_header=from_header)

    category = result.get("category", "general")
    if category in ("spam", "auto_reply", "no_response", "thank_you"):
        logger.info(f"Skipping {category}: {subject}")
        async with get_db_context() as db:
            agent_msg = AgentMessage(
                organization_id=organization_id,
                email_uid=uid,
                direction="inbound",
                from_email=from_email,
                to_email=to_header,
                subject=subject,
                body=body[:5000],
                category=category,
                urgency="low",
                status="ignored",
                customer_name=result.get("customer_name"),
                received_at=email_date,
                thread_id=thread.id,
                delivered_to=delivered_to_addr,
            )
            db.add(agent_msg)
            await db.commit()
        await update_thread_status(thread.id)
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

        agent_msg = AgentMessage(
            organization_id=organization_id,
            email_uid=uid,
            direction="inbound",
            from_email=from_email,
            to_email=to_header,
            subject=subject,
            body=body[:5000],
            category=category,
            urgency=result.get("urgency", "medium"),
            draft_response=result.get("draft_response"),
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
            action_confidence = action.get("confidence", "high")
            is_suggested = action_confidence in ("medium", "low")
            db.add(AgentAction(
                organization_id=organization_id,
                agent_message_id=agent_msg.id,
                thread_id=thread.id,
                action_type=action.get("action_type", "other"),
                description=action["description"],
                due_date=due_date,
                status="open",
                is_suggested=is_suggested,
                suggestion_confidence=action_confidence if is_suggested else None,
                created_by="DeepBlue",
            ))

        await db.commit()

        needs_approval = result.get("needs_approval", True)

        if needs_approval:
            # --- Flood protection: don't spam SMS for same sender ---
            if _should_throttle_alert(from_email):
                logger.info(f"Throttled SMS alert for {from_email} (cooldown)")
            elif not _is_business_hours():
                # --- Outside business hours: skip SMS, just log ---
                logger.info(f"Outside business hours, skipping SMS alert for: {subject}")
                agent_msg.notes = (agent_msg.notes or "") + "\nSMS alert suppressed (outside business hours)"
                agent_msg.notes = agent_msg.notes.strip()
                await db.commit()
            else:
                await send_approval_request(
                    agent_msg.id,
                    result.get("summary", subject),
                    result.get("draft_response", ""),
                    from_email,
                )
        else:
            # Auto-send
            draft = result.get("draft_response", "")
            success = await send_email_response(from_email, subject, draft)
            if success:
                agent_msg.status = "auto_sent"
                agent_msg.final_response = draft
                agent_msg.sent_at = datetime.now(timezone.utc)
                await db.commit()
                # Notify team (respect business hours + throttle)
                if _is_business_hours() and not _should_throttle_alert(f"auto_{from_email}"):
                    for number in APPROVAL_NUMBERS:
                        await send_sms(number, f"\U0001f4e4 Auto-replied to {from_email}: {result.get('summary', subject)[:100]}")

    # Update thread status
    await update_thread_status(thread.id)


async def handle_sms_reply(from_number: str, body: str):
    """Handle an incoming SMS reply (approval or modification)."""
    body = body.strip()

    # Find the pending approval
    ref = None
    for key in _pending_approvals:
        ref = key
        break  # Take the most recent pending

    if not ref or ref not in _pending_approvals:
        logger.warning(f"No pending approval found for SMS from {from_number}")
        return

    agent_msg_id = _pending_approvals.pop(ref)

    async with get_db_context() as db:
        result = await db.execute(
            select(AgentMessage).where(AgentMessage.id == agent_msg_id)
        )
        agent_msg = result.scalar_one_or_none()
        if not agent_msg:
            return

        if body.lower() in ("ok", "yes", "send", "approve", "y"):
            # Send the draft as-is
            response_text = agent_msg.draft_response
        elif body.lower() in ("no", "skip", "ignore", "n"):
            agent_msg.status = "rejected"
            await db.commit()
            await notify_others(from_number, f"Rejected: {agent_msg.subject}")
            return
        else:
            # Use the reply as instructions to redraft — include customer context
            customer_ctx = await match_customer(agent_msg.from_email, agent_msg.subject or "", agent_msg.body or "")
            redraft_system = f"You write email responses for {FROM_NAME}, a pool service company. Write a brief, professional response based on the instructions given. Sign as '{FROM_NAME}'. Keep it under 3 sentences."
            if customer_ctx:
                redraft_system += f"\n\nCustomer: {customer_ctx['customer_name']}"
                if customer_ctx.get("company_name"):
                    redraft_system += f" ({customer_ctx['company_name']})"
                if customer_ctx.get("preferred_day"):
                    redraft_system += f"\nService days: {customer_ctx['preferred_day']}"

            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            redraft = client.messages.create(
                model=await get_model("fast"),
                max_tokens=300,
                system=redraft_system,
                messages=[
                    {"role": "user", "content": f"Original email from {agent_msg.from_email}: {agent_msg.subject}\n\n{agent_msg.body[:500]}\n\nInstructions for response: {body}"}
                ],
            )
            response_text = redraft.content[0].text

        # Send the email
        success = await send_email_response(
            agent_msg.from_email,
            agent_msg.subject,
            response_text,
        )

        if success:
            agent_msg.status = "sent"
            agent_msg.final_response = response_text
            agent_msg.approved_by = from_number
            agent_msg.approved_at = datetime.now(timezone.utc)
            agent_msg.sent_at = datetime.now(timezone.utc)
            await db.commit()

            summary = f"{agent_msg.customer_name or agent_msg.from_email}: {agent_msg.subject}"
            await notify_others(from_number, summary)


async def save_discovered_contact(agent_msg_id: str):
    """When a message is confirmed (approved/sent), save the sender's email to the matched customer if missing."""
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentMessage).where(AgentMessage.id == agent_msg_id)
        )
        msg = result.scalar_one_or_none()
        if not msg or not msg.matched_customer_id:
            return

        cust_result = await db.execute(
            select(Customer).where(Customer.id == msg.matched_customer_id)
        )
        customer = cust_result.scalar_one_or_none()
        if not customer:
            return

        updated = False
        # Save email if customer doesn't have one
        if not customer.email and msg.from_email:
            customer.email = msg.from_email
            updated = True
            logger.info(f"Saved email {msg.from_email} to customer {customer.display_name}")

        # If customer has a different email, and this is a confirmed match,
        # log it but don't overwrite (might be a property manager emailing on behalf)
        if customer.email and customer.email.lower() != msg.from_email.lower():
            if not msg.notes:
                msg.notes = ""
            if msg.from_email not in (msg.notes or ""):
                msg.notes = (msg.notes + f"\nAlternate email: {msg.from_email}").strip()
                updated = True

        if updated:
            await db.commit()


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


async def _ai_triage(body: str, subject: str, from_email: str) -> bool:
    """Quick AI check: does this email need a response from us?

    Returns True if we should respond, False if it's informational/gratitude/FYI.
    Uses Haiku for speed — ~200ms per call.
    """
    if not body.strip():
        return False

    try:
        import anthropic
        from src.core.ai_models import get_model
        from src.core.config import get_settings
        settings = get_settings()
        if not settings.anthropic_api_key:
            return True  # Default to needing response if no AI

        model = await get_model("fast")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt = f"""You are triaging incoming emails for a pool service company.

From: {from_email}
Subject: {subject}
Body: {body[:500]}

Does this email require a response from us? Answer ONLY "yes" or "no".

Answer "no" if it's:
- A thank you, acknowledgment, or confirmation ("thanks", "got it", "sounds good")
- A status update that's just informational ("we expect to finish by May")
- An automated notification (order shipped, payment received)
- A marketing email or newsletter
- A forwarded message that's just FYI
- A one-word or very short affirmative ("ok", "yes", "perfect")

Answer "yes" if it's:
- Asking a question
- Requesting service, a quote, or scheduling
- Reporting a problem or complaint
- Asking for information we need to provide
- Requesting a callback or meeting"""

        response = await client.messages.create(
            model=model,
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip().lower()
        return answer.startswith("yes")

    except Exception as e:
        logger.warning(f"AI triage failed: {e}")
        return True  # Default to needing response on error


async def _process_sent_emails(org_id: str) -> int:
    """Track outbound emails sent via Gmail (not through the app).

    When someone replies from Gmail or an alias, the sent email
    appears in [Gmail]/Sent Mail. We match it to an existing thread
    and record it as an outbound message, marking the thread as handled.
    """
    from .mail_agent import fetch_sent_emails, mark_sent_processed, extract_text_body
    from .thread_manager import get_or_create_thread
    from src.models.agent_message import AgentMessage
    from src.models.agent_action import AgentAction, AgentActionComment
    from src.core.database import get_db_context
    import uuid as uuid_mod
    from email.utils import parsedate_to_datetime

    sent = fetch_sent_emails()
    if not sent:
        return 0

    count = 0
    for uid, msg in sent:
        try:
            from_email = msg.get("From", "")
            to_email = msg.get("To", "")
            subject = msg.get("Subject", "")

            # Only track emails FROM org addresses
            if not any(addr in from_email.lower() for addr in ["sapphire-pools.com", "sapphire_pools", "quantumpoolspro.com"]):
                mark_sent_processed(uid)
                continue

            # Skip emails sent to org addresses (internal)
            if not to_email or all(addr in to_email.lower() for addr in ["sapphire-pools.com", "quantumpoolspro.com"]):
                mark_sent_processed(uid)
                continue

            # Skip system emails (invites, password resets, etc.)
            subject_lower = (subject or "").lower()
            if any(skip in subject_lower for skip in ["invited to", "set up your", "password reset", "verify your", "welcome to"]):
                mark_sent_processed(uid)
                continue

            # Extract recipient email
            import re
            to_match = re.search(r'[\w.+-]+@[\w.-]+', to_email)
            if not to_match:
                mark_sent_processed(uid)
                continue
            recipient = to_match.group().lower()

            # Extract sender name
            from_match = re.match(r'"?([^"<]+)"?\s*<', from_email)
            sender_name = from_match.group(1).strip() if from_match else "Team"

            body = extract_text_body(msg)
            date_header = msg.get("Date")
            sent_at = parsedate_to_datetime(date_header) if date_header else datetime.now(timezone.utc)

            # Find or create thread
            thread = await get_or_create_thread(
                contact_email=recipient,
                subject=subject,
                organization_id=org_id,
            )

            # Check if we already recorded this (by checking for outbound message at same time)
            async with get_db_context() as db:
                existing = await db.execute(
                    select(AgentMessage).where(
                        AgentMessage.thread_id == thread.id,
                        AgentMessage.direction == "outbound",
                        AgentMessage.from_email.ilike(f"%{sender_name.split()[0]}%") if sender_name != "Team" else AgentMessage.id.isnot(None),
                        AgentMessage.subject == subject,
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    mark_sent_processed(uid)
                    continue

                # Record the outbound message
                outbound = AgentMessage(
                    id=str(uuid_mod.uuid4()),
                    organization_id=org_id,
                    direction="outbound",
                    from_email=from_email,
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    status="sent",
                    sent_at=sent_at,
                    received_at=sent_at,
                    thread_id=thread.id,
                )
                db.add(outbound)

                # Update thread — mark as handled since we replied
                thread_obj = (await db.execute(
                    select(AgentThread).where(AgentThread.id == thread.id)
                )).scalar_one_or_none()
                if thread_obj:
                    thread_obj.message_count = (thread_obj.message_count or 0) + 1
                    thread_obj.last_message_at = sent_at
                    thread_obj.last_direction = "outbound"
                    sent_clean = strip_email_signature(strip_quoted_reply(body or ""))
                    thread_obj.last_snippet = sent_clean[:200]
                    thread_obj.status = "handled"
                    thread_obj.has_pending = False

                # Link to open jobs on this thread
                if thread.id:
                    open_actions = (await db.execute(
                        select(AgentAction).where(
                            AgentAction.thread_id == thread.id,
                            AgentAction.organization_id == org_id,
                            AgentAction.status.in_(("open", "in_progress")),
                        )
                    )).scalars().all()
                    for action in open_actions:
                        comment = AgentActionComment(
                            organization_id=org_id,
                            action_id=action.id,
                            author=sender_name or "Team",
                            text=f"Email sent to {recipient}: {subject}",
                        )
                        db.add(comment)

                await db.commit()

            mark_sent_processed(uid)
            logger.info(f"Tracked sent email from {sender_name} to {recipient}: {subject[:50]}")
            count += 1

        except Exception as e:
            logger.error(f"Error tracking sent email {uid}: {e}", exc_info=True)
            mark_sent_processed(uid)  # Don't retry

    return count


async def run_poll_cycle():
    """Single poll cycle — check for new emails and process them."""
    org_id = await _get_default_org_id()
    if not org_id:
        logger.error("No organization found — cannot process emails")
        return 0

    messages = poll_inbox()
    if messages:
        logger.info(f"Found {len(messages)} new emails")
        for uid, msg in messages:
            try:
                await process_incoming_email(uid, msg, organization_id=org_id)
                mark_processed(uid)
            except Exception as e:
                logger.error(f"Error processing email {uid}: {e}", exc_info=True)

    # Also track outbound emails sent via Gmail
    try:
        sent_count = await _process_sent_emails(org_id)
        if sent_count:
            logger.info(f"Tracked {sent_count} sent emails")
    except Exception as e:
        logger.error(f"Error tracking sent emails: {e}", exc_info=True)

    # Auto-close stale visits (every 30 minutes, not every cycle)
    global _last_auto_close_check
    now = datetime.now(timezone.utc)
    should_check = (
        _last_auto_close_check is None
        or (now - _last_auto_close_check).total_seconds() >= AUTO_CLOSE_INTERVAL_MINUTES * 60
    )
    if should_check:
        _last_auto_close_check = now
        try:
            from src.services.visit_experience_service import VisitExperienceService
            async with get_db_context() as db:
                svc = VisitExperienceService(db)
                closed = await svc.auto_close_stale_visits(org_id)
                if closed:
                    logger.info(f"Auto-closed {closed} stale visit(s)")
                await db.commit()
        except Exception as e:
            logger.error(f"Error auto-closing stale visits: {e}", exc_info=True)

    return len(messages)
