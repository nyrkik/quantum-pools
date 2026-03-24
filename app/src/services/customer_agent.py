"""AI Customer Support Agent — reads emails, drafts responses, SMS approval flow."""

import os
import re
import json
import email
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

import aiosmtplib
import anthropic
from imapclient import IMAPClient
from twilio.rest import Client as TwilioClient

from sqlalchemy import select, desc, and_, or_, func
from sqlalchemy.orm import selectinload
from src.core.database import get_db_context
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction
from src.models.customer import Customer
from src.models.property import Property
from src.models.water_feature import WaterFeature

logger = logging.getLogger(__name__)

# Config from env
GMAIL_USER = os.environ.get("AGENT_GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("AGENT_GMAIL_PASSWORD", "")
IMAP_HOST = os.environ.get("AGENT_IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.environ.get("AGENT_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("AGENT_SMTP_PORT", "587"))
FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")
FROM_NAME = os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
APPROVAL_NUMBERS = [n.strip() for n in os.environ.get("AGENT_APPROVAL_NUMBERS", "").split(",") if n.strip()]

SYSTEM_PROMPT = """You are the AI assistant for Sapphire Pools, a commercial and residential pool service company in Sacramento, CA. You help manage client communications.

When classifying emails, respond with JSON:
{
  "category": "schedule|complaint|billing|gate_code|service_request|general|spam|auto_reply|no_response",
  "urgency": "low|medium|high",
  "customer_name": "extracted name or null",
  "summary": "one line summary",
  "needs_approval": true/false,
  "draft_response": "the response to send or null if no_response",
  "internal_note": "note for the team if any",
  "actions": [
    {
      "action_type": "follow_up|bid|schedule_change|site_visit|callback|repair|equipment|other",
      "description": "short description of what needs to happen",
      "due_days": 1
    }
  ]
}

Guidelines:
- category "auto_reply" means no-reply addresses, bounce notifications, marketing — ignore these
- category "spam" — junk, ignore
- category "no_response" — client emails that don't need a reply: "thank you", "thanks", "got it", "ok", "sounds good", "perfect", thumbs up, single-word acknowledgments, forwarded FYI emails with no question. Log but don't draft a response or alert anyone.
- needs_approval = false ONLY for: gate code confirmations where no action needed
- needs_approval = true for: schedule changes, complaints, billing questions, service requests, anything requiring a decision or a real reply
- Draft responses should be warm, professional, concise. Sign as "Sapphire Pools" not a specific person.
- Never promise specific dates/times without approval
- If the email mentions a property name you recognize, include it in the response
- Keep responses under 3 sentences unless the situation requires more

CRITICAL TONE RULES — follow these exactly:
- NEVER admit fault, accept blame, or apologize for service failures. No "we apologize", "we're sorry", "that's not our standard", "we dropped the ball", etc.
- Keep responses neutral and fact-finding. Focus on gathering information and next steps, not explaining what went wrong.
- When a client complains, respond with concern but DO NOT validate their version of events. There are always two sides.
- Use phrases like "let me look into this", "I'd like to get some details", "let me check on your account", "we'll get back to you with an update"
- Never say "you're right" or "that shouldn't have happened" — instead redirect to resolution
- Be friendly and helpful, but protect the company's position at all times
- Address clients by first name if known, or "Hi" with their name. Use the contact name from the customer record when available.
- Don't use "family" as a suffix (e.g., "Blomquist family"). Just use their name.
- Don't over-promise urgency. "We'll look into this" or "we'll follow up" is fine — avoid "prioritizing", "right away", "ASAP" unless truly critical.
- Format draft_response as a proper email: greeting on its own line, body paragraphs separated by blank lines, then the signature. Use \\n for line breaks in the JSON string.
- Always end with this exact signature (no variations):\\n\\nBest,\\nThe Sapphire Pools Team\\ncontact@sapphire-pools.com
- "actions" array: extract follow-up work the team needs to do. ONE action per distinct task — do NOT split a single task into steps. For example, "inspect pool and report back" is ONE action, not two. Include due_days (business days). Leave empty [] if no action needed.
- Common action types: "bid" (send a quote/proposal), "follow_up" (check back with client), "schedule_change" (modify service day/frequency), "site_visit" (go inspect/assess), "callback" (phone call needed), "repair" (fix equipment/issue), "equipment" (order/replace equipment)
- Keep action descriptions concise — what needs to happen, not how to do it"""

# Track pending approvals: message_id -> AgentMessage.id
_pending_approvals: dict[str, str] = {}

# Flood protection: track recent SMS alerts per sender
_recent_alerts: dict[str, datetime] = {}
ALERT_COOLDOWN_MINUTES = 10

# Business hours (Pacific time)
BUSINESS_HOUR_START = 7  # 7 AM
BUSINESS_HOUR_END = 20   # 8 PM

# Reply loop detection patterns
LOOP_PATTERNS = ["noreply@", "no-reply@", "mailer-daemon@", "postmaster@"]


def _is_own_email(from_email: str) -> bool:
    """Check if the email is from one of our own addresses (reply loop prevention)."""
    addr = from_email.lower().strip()
    # Check our own sending addresses
    if FROM_EMAIL and addr == FROM_EMAIL.lower():
        return True
    if GMAIL_USER and addr == GMAIL_USER.lower():
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


def _normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes for thread matching."""
    s = subject.strip()
    while True:
        lower = s.lower()
        if lower.startswith("re:"):
            s = s[3:].strip()
        elif lower.startswith("fwd:"):
            s = s[4:].strip()
        elif lower.startswith("fw:"):
            s = s[3:].strip()
        else:
            break
    return s


async def _find_thread(from_email: str, subject: str, message_id_header: str | None = None) -> AgentMessage | None:
    """Find the most recent message in the same thread (same sender + normalized subject)."""
    normalized = _normalize_subject(subject)
    if not normalized:
        return None

    async with get_db_context() as db:
        # Look for recent messages from same sender with same base subject
        result = await db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.from_email == from_email,
                AgentMessage.status.in_(("sent", "auto_sent", "pending")),
            )
            .order_by(desc(AgentMessage.received_at))
            .limit(10)
        )
        for msg in result.scalars().all():
            if msg.subject and _normalize_subject(msg.subject) == normalized:
                return msg
    return None


async def _get_thread_open_actions(thread_msg: AgentMessage) -> list[str]:
    """Get descriptions of open action items for a thread message."""
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentAction)
            .where(
                AgentAction.agent_message_id == thread_msg.id,
                AgentAction.status.in_(("open", "in_progress")),
            )
        )
        return [a.description for a in result.scalars().all()]


def decode_email_header(header):
    """Decode email header handling various encodings."""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _clean_html(html: str) -> str:
    """Convert HTML to clean plain text."""
    from html import unescape
    # Replace block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|tr|li|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (&nbsp; &amp; etc)
    text = unescape(text)
    # Collapse whitespace within lines but preserve line breaks
    lines = text.split("\n")
    lines = [" ".join(line.split()) for line in lines]
    # Remove excessive blank lines
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_body(msg) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback to HTML if no plain text
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return _clean_html(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                return _clean_html(text)
            return text
    return ""


def _extract_sender_name(from_header: str) -> str | None:
    """Extract the display name from a From header like 'John Smith <john@example.com>'."""
    # Try to get the name part before the email
    match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
    if match:
        name = match.group(1).strip()
        if name and "@" not in name:
            return name
    return None


async def match_customer(from_email: str, subject: str, body: str, from_header: str = "") -> dict | None:
    """Match an incoming email to a customer in the database. Returns context dict or None."""
    match_method = None

    async with get_db_context() as db:
        customer = None

        # 1. Direct email match
        result = await db.execute(
            select(Customer).where(
                func.lower(Customer.email) == from_email.lower(),
                Customer.is_active == True,
            )
        )
        customer = result.scalar_one_or_none()
        if customer:
            match_method = "email"

        # 2. Check previous messages — if we've matched this email before, reuse it
        if not customer:
            prev = await db.execute(
                select(AgentMessage).where(
                    AgentMessage.from_email == from_email,
                    AgentMessage.matched_customer_id.isnot(None),
                ).order_by(desc(AgentMessage.received_at)).limit(1)
            )
            prev_msg = prev.scalar_one_or_none()
            if prev_msg:
                cust_result = await db.execute(
                    select(Customer).where(Customer.id == prev_msg.matched_customer_id)
                )
                customer = cust_result.scalar_one_or_none()
                if customer:
                    match_method = "previous_match"

        # 3. Domain match (for property managers — same @company.com)
        multi_match_customers = None
        if not customer:
            domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
            if domain and domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "protonmail.com", "me.com"):
                result = await db.execute(
                    select(Customer).where(
                        Customer.email.ilike(f"%@{domain}"),
                        Customer.is_active == True,
                    ).limit(10)
                )
                domain_matches = result.scalars().all()
                if len(domain_matches) == 1:
                    customer = domain_matches[0]
                    match_method = "domain"
                elif len(domain_matches) > 1:
                    # Multiple customers with same domain — store for Claude to disambiguate
                    multi_match_customers = domain_matches
                    match_method = "domain_multi"

        # 4. Sender name match — extract name from "From: John Smith <john@example.com>"
        if not customer:
            sender_name = _extract_sender_name(from_header) if from_header else None
            if not sender_name:
                # Try extracting from email prefix: john.smith@... -> John Smith
                prefix = from_email.split("@")[0] if "@" in from_email else ""
                parts = re.split(r'[._-]', prefix)
                if len(parts) >= 2 and all(p.isalpha() for p in parts[:2]):
                    sender_name = " ".join(p.capitalize() for p in parts[:2])

            if sender_name:
                name_parts = sender_name.strip().split()
                if len(name_parts) >= 2:
                    first = name_parts[0]
                    last = name_parts[-1]
                    result = await db.execute(
                        select(Customer).where(
                            Customer.is_active == True,
                            func.lower(Customer.first_name) == first.lower(),
                            func.lower(Customer.last_name) == last.lower(),
                        ).limit(1)
                    )
                    customer = result.scalar_one_or_none()
                    if customer:
                        match_method = "sender_name"
                elif len(name_parts) == 1:
                    # Single name — try last name match (more unique than first)
                    result = await db.execute(
                        select(Customer).where(
                            Customer.is_active == True,
                            func.lower(Customer.last_name) == name_parts[0].lower(),
                        )
                    )
                    matches = result.scalars().all()
                    if len(matches) == 1:  # Only use if unambiguous
                        customer = matches[0]
                        match_method = "sender_name"

        # 5. Search subject/body for known company names
        if not customer:
            text_to_search = f"{subject} {body[:1000]}".lower()
            result = await db.execute(
                select(Customer).where(
                    Customer.is_active == True,
                    Customer.company_name.isnot(None),
                )
            )
            for c in result.scalars().all():
                if c.company_name and len(c.company_name) > 3 and c.company_name.lower() in text_to_search:
                    customer = c
                    match_method = "company_name"
                    break

        # 6. Search subject/body for customer last names (only if unique match)
        if not customer:
            text_to_search = f"{subject} {body[:1000]}".lower()
            result = await db.execute(
                select(Customer).where(Customer.is_active == True)
            )
            all_customers = result.scalars().all()
            name_matches = []
            for c in all_customers:
                if c.last_name and len(c.last_name) > 2 and c.last_name.lower() in text_to_search:
                    name_matches.append(c)
            if len(name_matches) == 1:  # Only use if unambiguous
                customer = name_matches[0]
                match_method = "body_name"

        if not customer and not multi_match_customers:
            return None

        # Multi-match: build context for all candidates, let Claude disambiguate
        if not customer and multi_match_customers:
            candidates = []
            for c in multi_match_customers:
                props_result = await db.execute(
                    select(Property).where(Property.customer_id == c.id, Property.is_active == True)
                )
                props = props_result.scalars().all()
                addresses = [p.full_address for p in props]
                candidates.append({
                    "customer_id": c.id,
                    "name": c.display_name,
                    "company": c.company_name,
                    "addresses": addresses,
                })
            return {
                "customer_id": None,
                "match_method": "domain_multi",
                "customer_name": None,
                "customer_type": multi_match_customers[0].customer_type,
                "company_name": multi_match_customers[0].company_name,
                "email": from_email,
                "phone": None,
                "preferred_day": None,
                "monthly_rate": None,
                "notes": None,
                "properties": [],
                "property_address": None,
                "_multi_candidates": candidates,
            }

        # Build context
        props_result = await db.execute(
            select(Property).where(
                Property.customer_id == customer.id,
                Property.is_active == True,
            )
        )
        properties = props_result.scalars().all()

        prop_contexts = []
        for prop in properties:
            wf_result = await db.execute(
                select(WaterFeature).where(
                    WaterFeature.property_id == prop.id,
                    WaterFeature.is_active == True,
                )
            )
            water_features = wf_result.scalars().all()

            wf_lines = []
            for wf in water_features:
                parts = [f"{wf.name or wf.water_type}"]
                if wf.pool_gallons:
                    parts.append(f"{wf.pool_gallons:,} gal")
                if wf.sanitizer_type:
                    parts.append(f"sanitizer: {wf.sanitizer_type}")
                if wf.estimated_service_minutes:
                    parts.append(f"{wf.estimated_service_minutes} min service")
                if wf.monthly_rate:
                    parts.append(f"${wf.monthly_rate:.2f}/mo")
                wf_lines.append(", ".join(parts))

            p_parts = [prop.full_address]
            if prop.gate_code:
                p_parts.append(f"Gate: {prop.gate_code}")
            if prop.dog_on_property:
                p_parts.append("DOG on property")
            if prop.access_instructions:
                p_parts.append(f"Access: {prop.access_instructions}")
            if prop.notes:
                p_parts.append(f"Notes: {prop.notes}")

            prop_ctx = " | ".join(p_parts)
            if wf_lines:
                prop_ctx += "\n    Bodies of water: " + "; ".join(wf_lines)
            prop_contexts.append(prop_ctx)

        ctx = {
            "customer_id": customer.id,
            "match_method": match_method,
            "customer_name": customer.display_name,
            "customer_type": customer.customer_type,
            "company_name": customer.company_name,
            "email": customer.email,
            "phone": customer.phone,
            "preferred_day": customer.preferred_day,
            "monthly_rate": customer.monthly_rate,
            "notes": customer.notes,
            "properties": prop_contexts,
            "property_address": properties[0].full_address if properties else None,
        }
        return ctx


async def get_correction_history(from_email: str, category: str | None) -> list[dict]:
    """Get past corrections (edited drafts) to learn from. Returns most relevant examples."""
    async with get_db_context() as db:
        # Get messages where draft was edited before sending (final != draft)
        query = (
            select(AgentMessage)
            .where(
                AgentMessage.status == "sent",
                AgentMessage.draft_response.isnot(None),
                AgentMessage.final_response.isnot(None),
                AgentMessage.draft_response != AgentMessage.final_response,
            )
            .order_by(desc(AgentMessage.sent_at))
            .limit(20)
        )
        result = await db.execute(query)
        edited = result.scalars().all()

        # Also get rejections to learn what NOT to do
        reject_query = (
            select(AgentMessage)
            .where(AgentMessage.status == "rejected")
            .order_by(desc(AgentMessage.approved_at))
            .limit(5)
        )
        reject_result = await db.execute(reject_query)
        rejected = reject_result.scalars().all()

        # Also get recent successful sends for same email (conversation continuity)
        convo_query = (
            select(AgentMessage)
            .where(
                AgentMessage.from_email == from_email,
                AgentMessage.status.in_(("sent", "auto_sent")),
            )
            .order_by(desc(AgentMessage.sent_at))
            .limit(5)
        )
        convo_result = await db.execute(convo_query)
        past_convos = convo_result.scalars().all()

        corrections = []

        # Prioritize: same-email corrections, then same-category, then general
        for msg in edited:
            relevance = "general"
            if msg.from_email == from_email:
                relevance = "same_client"
            elif msg.category == category:
                relevance = "same_category"
            corrections.append({
                "type": "correction",
                "relevance": relevance,
                "category": msg.category,
                "subject": msg.subject,
                "original_draft": msg.draft_response[:200],
                "corrected_to": msg.final_response[:200],
            })

        # Sort: same_client first, then same_category, then general
        priority = {"same_client": 0, "same_category": 1, "general": 2}
        corrections.sort(key=lambda x: priority.get(x["relevance"], 3))

        for msg in rejected:
            corrections.append({
                "type": "rejection",
                "category": msg.category,
                "subject": msg.subject,
                "rejected_draft": msg.draft_response[:200] if msg.draft_response else "",
                "reason": "Team decided not to respond",
            })

        past_exchanges = []
        for msg in past_convos:
            past_exchanges.append({
                "subject": msg.subject,
                "received": msg.received_at.isoformat() if msg.received_at else None,
                "response": msg.final_response[:200] if msg.final_response else msg.draft_response[:200] if msg.draft_response else "",
            })

        return {
            "corrections": corrections[:8],  # Cap at 8 most relevant
            "past_exchanges": past_exchanges,
        }


def build_context_prompt(customer_ctx: dict | None, history: dict | None) -> str:
    """Build the context section to inject into the system prompt."""
    parts = []

    if customer_ctx and customer_ctx.get("_multi_candidates"):
        candidates = customer_ctx["_multi_candidates"]
        parts.append("=== MULTIPLE POSSIBLE CUSTOMERS ===")
        parts.append(f"The sender's email domain matches {len(candidates)} customers. Determine which one based on the email content:")
        for i, c in enumerate(candidates, 1):
            addrs = ", ".join(c["addresses"][:3]) if c["addresses"] else "no properties"
            parts.append(f"  {i}. {c['name']}{' (' + c['company'] + ')' if c.get('company') else ''} — {addrs}")
        parts.append("")
        parts.append("In your JSON response, set customer_name to the matched customer's name. If you cannot determine which customer, set customer_name to null and add an internal_note explaining the ambiguity.")

    elif customer_ctx:
        parts.append("=== KNOWN CUSTOMER ===")
        parts.append(f"Name: {customer_ctx['customer_name']}")
        parts.append(f"Type: {customer_ctx['customer_type']}")
        if customer_ctx.get("company_name"):
            parts.append(f"Company: {customer_ctx['company_name']}")
        if customer_ctx.get("phone"):
            parts.append(f"Phone: {customer_ctx['phone']}")
        if customer_ctx.get("preferred_day"):
            parts.append(f"Service days: {customer_ctx['preferred_day']}")
        if customer_ctx.get("monthly_rate"):
            parts.append(f"Rate: ${customer_ctx['monthly_rate']:.2f}/mo")
        if customer_ctx.get("notes"):
            parts.append(f"Customer notes: {customer_ctx['notes']}")
        for i, prop in enumerate(customer_ctx.get("properties", [])):
            parts.append(f"Property {i+1}: {prop}")
        parts.append("")
        parts.append("Use the customer's name and reference their property details when relevant. This is a known client — respond with familiarity, not as a cold contact.")

    if history:
        exchanges = history.get("past_exchanges", [])
        if exchanges:
            parts.append("")
            parts.append("=== RECENT CONVERSATION HISTORY ===")
            for ex in exchanges[:3]:
                parts.append(f"- [{ex.get('received', '?')}] Re: {ex['subject']}")
                parts.append(f"  Our reply: {ex['response']}")
            parts.append("")
            parts.append("Continue the existing relationship tone. Reference prior communication if relevant.")

        corrections = history.get("corrections", [])
        if corrections:
            parts.append("")
            parts.append("=== LEARN FROM PAST CORRECTIONS ===")
            parts.append("The team has previously edited drafts. Adapt your style based on these:")
            for c in corrections[:5]:
                if c["type"] == "correction":
                    parts.append(f"- [{c.get('category', '?')}] Draft: \"{c['original_draft']}\"")
                    parts.append(f"  Corrected to: \"{c['corrected_to']}\"")
                elif c["type"] == "rejection":
                    parts.append(f"- [{c.get('category', '?')}] REJECTED draft for: {c['subject']}")
                    parts.append(f"  Draft was: \"{c.get('rejected_draft', '')}\"")
            parts.append("")
            parts.append("Match the corrected tone and style. Avoid patterns from rejected drafts.")

    return "\n".join(parts) if parts else ""


async def classify_and_draft(from_email: str, subject: str, body: str, from_header: str = "") -> dict:
    """Use Claude to classify the email and draft a response with customer context and learning."""
    # Build context from database
    customer_ctx = await match_customer(from_email, subject, body, from_header)
    history = await get_correction_history(from_email, None)

    context_block = build_context_prompt(customer_ctx, history)

    full_system = SYSTEM_PROMPT
    if context_block:
        full_system += "\n\n" + context_block

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    user_msg = f"From: {from_email}\nSubject: {subject}\n\n{body[:2000]}"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=full_system,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text
    # Parse JSON from response
    try:
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            # Enrich with matched customer data
            if customer_ctx:
                # Handle multi-match: Claude picks the customer by name
                if customer_ctx.get("_multi_candidates") and result.get("customer_name"):
                    picked_name = result["customer_name"].lower()
                    for c in customer_ctx["_multi_candidates"]:
                        if c["name"].lower() in picked_name or picked_name in c["name"].lower():
                            result["_matched_customer_id"] = c["customer_id"]
                            result["_match_method"] = "domain_multi"
                            # Get property address
                            if c.get("addresses"):
                                result["_property_address"] = c["addresses"][0]
                            break
                    if not result.get("_matched_customer_id"):
                        result["_match_method"] = "domain_multi_unresolved"
                elif customer_ctx.get("customer_id"):
                    if not result.get("customer_name"):
                        result["customer_name"] = customer_ctx["customer_name"]
                    result["_matched_customer_id"] = customer_ctx["customer_id"]
                    result["_match_method"] = customer_ctx["match_method"]
                    result["_property_address"] = customer_ctx.get("property_address")
            return result
    except json.JSONDecodeError:
        pass

    result = {
        "category": "general",
        "urgency": "medium",
        "customer_name": customer_ctx["customer_name"] if customer_ctx else None,
        "summary": subject,
        "needs_approval": True,
        "draft_response": "Thank you for reaching out. We'll get back to you shortly.",
        "internal_note": "Failed to parse AI response",
    }
    if customer_ctx:
        result["_matched_customer_id"] = customer_ctx["customer_id"]
        result["_match_method"] = customer_ctx["match_method"]
        result["_property_address"] = customer_ctx.get("property_address")
    return result


async def send_sms(to: str, body: str):
    """Send SMS via Twilio."""
    try:
        client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(
            body=body,
            from_=TWILIO_NUMBER,
            to=to,
        )
        logger.info(f"SMS sent to {to}: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS to {to}: {e}")
        return False


async def send_approval_request(agent_msg_id: str, summary: str, draft: str, from_email: str):
    """Send SMS to all approval numbers."""
    # Truncate for SMS (160 char limit per segment)
    text = f"📧 {from_email}\n{summary}\n\nDraft: \"{draft[:200]}\"\n\nReply OK to send, or reply with changes.\nRef: {agent_msg_id[:8]}"

    _pending_approvals[agent_msg_id[:8]] = agent_msg_id

    for number in APPROVAL_NUMBERS:
        await send_sms(number, text)


async def send_email_response(to: str, subject: str, body: str):
    """Send email reply via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
    msg.attach(MIMEText(body, "plain"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=GMAIL_USER,
            password=GMAIL_PASSWORD,
            start_tls=True,
        )
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


async def notify_others(approver: str, summary: str):
    """Notify other team members that someone approved."""
    name_map = {}
    for n in APPROVAL_NUMBERS:
        if n.endswith("1085"):
            name_map[n] = "Brian"
        elif n.endswith("6729"):
            name_map[n] = "Chance"
        elif n.endswith("1260"):
            name_map[n] = "Kim"

    approver_name = name_map.get(approver, approver)
    for number in APPROVAL_NUMBERS:
        if number != approver:
            await send_sms(number, f"✅ {approver_name} handled: {summary[:100]}")


async def process_incoming_email(uid: str, msg):
    """Process a single incoming email."""
    from_header = decode_email_header(msg.get("From", ""))
    subject = decode_email_header(msg.get("Subject", ""))
    body = extract_text_body(msg)
    message_id_header = msg.get("Message-ID", "")

    # Extract email address from From header
    email_match = re.search(r"<(.+?)>", from_header)
    from_email = email_match.group(1) if email_match else from_header

    to_header = decode_email_header(msg.get("To", ""))

    # --- Reply loop prevention ---
    if _is_own_email(from_email):
        logger.info(f"Skipping own email: {from_email}: {subject}")
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

    # --- Thread detection ---
    thread_parent = await _find_thread(from_email, subject, message_id_header)
    thread_context = ""
    existing_action_descriptions = []
    if thread_parent:
        logger.info(f"Thread detected: reply to message {thread_parent.id[:8]}")
        # Build thread context for Claude
        thread_context = f"\n\n=== THIS IS A FOLLOW-UP ===\nThis email is a reply in an existing thread. Previous message status: {thread_parent.status}."
        if thread_parent.final_response:
            thread_context += f"\nOur last reply: {thread_parent.final_response[:300]}"
        elif thread_parent.draft_response:
            thread_context += f"\nDraft (not yet sent): {thread_parent.draft_response[:300]}"
        thread_context += "\nDo NOT create duplicate action items. Only add new actions if this email introduces genuinely new work."
        # Get existing actions to prevent duplicates
        existing_action_descriptions = await _get_thread_open_actions(thread_parent)

    # Classify and draft
    result = await classify_and_draft(from_email, subject, body + thread_context, from_header=from_header)

    category = result.get("category", "general")
    if category in ("spam", "auto_reply", "no_response"):
        logger.info(f"Skipping {category}: {subject}")
        async with get_db_context() as db:
            agent_msg = AgentMessage(
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
            )
            db.add(agent_msg)
            await db.commit()
        return

    # Save to DB
    async with get_db_context() as db:
        agent_msg = AgentMessage(
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
            matched_customer_id=result.get("_matched_customer_id"),
            match_method=result.get("_match_method"),
            customer_name=result.get("customer_name"),
            property_address=result.get("_property_address"),
            notes=result.get("internal_note"),
        )
        db.add(agent_msg)
        await db.flush()

        # Create action items — skip duplicates from thread
        actions = result.get("actions", [])
        for action in actions:
            if not action.get("description"):
                continue
            # Skip if similar action already exists in thread
            desc_lower = action["description"].lower()
            is_duplicate = False
            for existing_desc in existing_action_descriptions:
                # Fuzzy match: if >60% of words overlap, it's a duplicate
                existing_words = set(existing_desc.lower().split())
                new_words = set(desc_lower.split())
                if existing_words and new_words:
                    overlap = len(existing_words & new_words) / max(len(existing_words), len(new_words))
                    if overlap > 0.6:
                        is_duplicate = True
                        logger.info(f"Skipping duplicate action: {action['description'][:60]}")
                        break
            if is_duplicate:
                continue

            due_days = action.get("due_days", 3)
            due_date = datetime.now(timezone.utc) + timedelta(days=due_days) if due_days else None
            db.add(AgentAction(
                agent_message_id=agent_msg.id,
                action_type=action.get("action_type", "other"),
                description=action["description"],
                due_date=due_date,
                status="open",
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
                        await send_sms(number, f"📤 Auto-replied to {from_email}: {result.get('summary', subject)[:100]}")


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
            redraft_system = "You write email responses for Sapphire Pools, a pool service company. Write a brief, professional response based on the instructions given. Sign as 'Sapphire Pools'. Keep it under 3 sentences."
            if customer_ctx:
                redraft_system += f"\n\nCustomer: {customer_ctx['customer_name']}"
                if customer_ctx.get("company_name"):
                    redraft_system += f" ({customer_ctx['company_name']})"
                if customer_ctx.get("preferred_day"):
                    redraft_system += f"\nService days: {customer_ctx['preferred_day']}"

            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            redraft = client.messages.create(
                model="claude-haiku-4-5-20251001",
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


async def evaluate_next_action(action_id: str) -> dict | None:
    """When an action is completed, use Claude to evaluate if a follow-up is needed.
    Returns a recommended action dict or None."""
    async with get_db_context() as db:
        # Load the completed action + parent message + all sibling actions
        action_result = await db.execute(
            select(AgentAction).where(AgentAction.id == action_id)
        )
        action = action_result.scalar_one_or_none()
        if not action:
            return None

        msg_result = await db.execute(
            select(AgentMessage).where(AgentMessage.id == action.agent_message_id)
        )
        msg = msg_result.scalar_one_or_none()
        if not msg:
            return None

        # Get all actions for this message with comments
        from sqlalchemy.orm import selectinload
        siblings_result = await db.execute(
            select(AgentAction)
            .options(selectinload(AgentAction.comments))
            .where(AgentAction.agent_message_id == msg.id)
        )
        all_actions = siblings_result.scalars().all()

        # Build context for Claude
        actions_summary = []
        for a in all_actions:
            status_label = a.status
            if a.id == action_id:
                status_label = "JUST COMPLETED"
            line = f"- [{status_label}] {a.action_type}: {a.description}"
            if a.notes:
                line += f"\n  Notes: {a.notes}"
            if a.comments:
                for c in a.comments:
                    line += f"\n  Comment ({c.author}): {c.text}"
            actions_summary.append(line)

        # Get customer context if matched
        customer_info = ""
        if msg.matched_customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == msg.matched_customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            if customer:
                customer_info = f"\nCustomer: {customer.display_name} ({customer.customer_type})"
                if customer.company_name:
                    customer_info += f" — {customer.company_name}"

    # Check if a follow-up was recently sent
    followup_note = ""
    if msg.notes and "Follow-up sent" in msg.notes:
        followup_note = f"\n\nIMPORTANT: A follow-up email was already sent to the client. Notes: {msg.notes}"

    prompt = f"""An action item was just completed for a pool service company. Based on the context, determine if there is a logical next step.

Original email from {msg.from_email}:
Subject: {msg.subject}
{msg.body[:500] if msg.body else 'No body'}
{customer_info}

Our response: {msg.final_response[:300] if msg.final_response else msg.draft_response[:300] if msg.draft_response else 'Not yet responded'}{followup_note}

Action items for this event:
{chr(10).join(actions_summary)}

Based on the completed action and the overall situation, is there a natural next step?

Respond with JSON:
{{
  "has_next": true/false,
  "action_type": "follow_up|bid|schedule_change|site_visit|callback|repair|equipment|other",
  "description": "what needs to happen next",
  "due_days": 3,
  "reasoning": "why this is the logical next step"
}}

Rules:
- Only recommend a next step if it's genuinely needed — don't create busywork
- If all necessary work is covered by existing open actions, return has_next: false
- If a follow-up email was already sent to the client about this issue, do NOT suggest calling or emailing them again about the same thing
- Common patterns: site_visit done → report findings to client or schedule repair; repair done → follow up to confirm satisfaction; bid sent → follow up if no response in a few days
- Keep description concise — one task, not multiple steps"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if result.get("has_next"):
                return {
                    "agent_message_id": msg.id,
                    "action_type": result.get("action_type", "follow_up"),
                    "description": result.get("description", ""),
                    "due_days": result.get("due_days", 3),
                    "reasoning": result.get("reasoning", ""),
                }
    except Exception as e:
        logger.error(f"Failed to evaluate next action: {e}")

    return None


QP_LABEL = "QP-Processed"
_label_ensured = False


def _ensure_label(client: IMAPClient):
    """Create the QP-Processed label if it doesn't exist."""
    global _label_ensured
    if _label_ensured:
        return
    try:
        folders = [f[2] for f in client.list_folders()]
        if QP_LABEL not in folders:
            client.create_folder(QP_LABEL)
            logger.info(f"Created Gmail label: {QP_LABEL}")
        _label_ensured = True
    except Exception as e:
        logger.error(f"Failed to ensure label: {e}")
        _label_ensured = True  # Don't retry every cycle


def poll_inbox():
    """Connect to Gmail IMAP and fetch emails not yet processed by QP.
    Uses a Gmail label instead of UNSEEN to avoid missing emails opened elsewhere."""
    messages = []
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)

        _ensure_label(client)

        client.select_folder("INBOX")

        # Search for emails NOT labeled QP-Processed
        # Gmail IMAP uses X-GM-LABELS for label queries
        uids = client.gmail_search(f"-label:{QP_LABEL} newer_than:2d")
        if not uids:
            client.logout()
            return []

        # Fetch only the newest 10 to avoid overload
        uids = uids[-10:]
        raw_messages = client.fetch(uids, ["RFC822"])

        for uid, data in raw_messages.items():
            raw = data[b"RFC822"]
            msg = email.message_from_bytes(raw)
            messages.append((str(uid), msg))

        client.logout()
    except Exception as e:
        logger.error(f"IMAP error: {e}")

    return messages


def mark_processed(uid: str):
    """Add the QP-Processed label to a message after processing."""
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)
        client.select_folder("INBOX")

        # Add the label using Gmail's IMAP extension
        client.add_gmail_labels([int(uid)], [QP_LABEL])

        client.logout()
    except Exception as e:
        logger.error(f"Failed to mark processed {uid}: {e}")


async def run_poll_cycle():
    """Single poll cycle — check for new emails and process them."""
    messages = poll_inbox()
    if messages:
        logger.info(f"Found {len(messages)} new emails")
        for uid, msg in messages:
            try:
                await process_incoming_email(uid, msg)
                mark_processed(uid)
            except Exception as e:
                logger.error(f"Error processing email {uid}: {e}")
    return len(messages)
