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
  "category": "schedule|complaint|billing|gate_code|service_request|general|spam|auto_reply",
  "urgency": "low|medium|high",
  "customer_name": "extracted name or null",
  "summary": "one line summary",
  "needs_approval": true/false,
  "draft_response": "the response to send",
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
- needs_approval = false ONLY for: simple acknowledgments, "we received your message", gate code confirmations where no action needed
- needs_approval = true for: schedule changes, complaints, billing questions, service requests, anything requiring a decision
- Draft responses should be warm, professional, concise. Sign as "Sapphire Pools" not a specific person.
- Never promise specific dates/times without approval
- If the email mentions a property name you recognize, include it in the response
- Keep responses under 3 sentences unless the situation requires more
- "actions" array: extract ANY follow-up work the team needs to do (send a bid, schedule a visit, call back, repair something, change schedule). Include due_days (business days). Leave empty [] if no action needed.
- Common action types: "bid" (send a quote/proposal), "follow_up" (check back with client), "schedule_change" (modify service day/frequency), "site_visit" (go inspect/assess), "callback" (phone call needed), "repair" (fix equipment/issue), "equipment" (order/replace equipment)"""

# Track pending approvals: message_id -> AgentMessage.id
_pending_approvals: dict[str, str] = {}


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
                    html = payload.decode(charset, errors="replace")
                    # Strip HTML tags roughly
                    return re.sub(r"<[^>]+>", " ", html).strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


async def match_customer(from_email: str, subject: str, body: str) -> dict | None:
    """Match an incoming email to a customer in the database. Returns context dict or None."""
    async with get_db_context() as db:
        # 1. Direct email match
        result = await db.execute(
            select(Customer).where(
                func.lower(Customer.email) == from_email.lower(),
                Customer.is_active == True,
            )
        )
        customer = result.scalar_one_or_none()

        # 2. Fuzzy: check if from_email domain matches any customer email domain (for property managers)
        if not customer:
            domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
            if domain and domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"):
                result = await db.execute(
                    select(Customer).where(
                        Customer.email.ilike(f"%@{domain}"),
                        Customer.is_active == True,
                    ).limit(1)
                )
                customer = result.scalar_one_or_none()

        # 3. Search subject/body for known company names or addresses
        if not customer:
            text_to_search = f"{subject} {body[:1000]}".lower()
            result = await db.execute(
                select(Customer).where(
                    Customer.is_active == True,
                    Customer.company_name.isnot(None),
                )
            )
            for c in result.scalars().all():
                if c.company_name and c.company_name.lower() in text_to_search:
                    customer = c
                    break

        if not customer:
            return None

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

    if customer_ctx:
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


async def classify_and_draft(from_email: str, subject: str, body: str) -> dict:
    """Use Claude to classify the email and draft a response with customer context and learning."""
    # Build context from database
    customer_ctx = await match_customer(from_email, subject, body)
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
                if not result.get("customer_name"):
                    result["customer_name"] = customer_ctx["customer_name"]
                result["_matched_customer_id"] = customer_ctx["customer_id"]
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

    # Extract email address from From header
    email_match = re.search(r"<(.+?)>", from_header)
    from_email = email_match.group(1) if email_match else from_header

    to_header = decode_email_header(msg.get("To", ""))

    logger.info(f"Processing email from {from_email}: {subject}")

    # Check if already processed
    async with get_db_context() as db:
        existing = await db.execute(
            select(AgentMessage).where(AgentMessage.email_uid == uid)
        )
        if existing.scalar_one_or_none():
            logger.info(f"Already processed: {uid}")
            return

    # Classify and draft
    result = await classify_and_draft(from_email, subject, body)

    category = result.get("category", "general")
    if category in ("spam", "auto_reply"):
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
            customer_name=result.get("customer_name"),
            property_address=result.get("_property_address"),
            notes=result.get("internal_note"),
        )
        db.add(agent_msg)
        await db.flush()

        # Create action items if any
        actions = result.get("actions", [])
        for action in actions:
            if not action.get("description"):
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
                # Notify team
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


def poll_inbox():
    """Connect to Gmail IMAP and fetch unread emails. Returns list of (uid, email.message)."""
    messages = []
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)
        client.select_folder("INBOX")

        # Get unread messages
        uids = client.search(["UNSEEN"])
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


async def run_poll_cycle():
    """Single poll cycle — check for new emails and process them."""
    messages = poll_inbox()
    if messages:
        logger.info(f"Found {len(messages)} new emails")
        for uid, msg in messages:
            try:
                await process_incoming_email(uid, msg)
            except Exception as e:
                logger.error(f"Error processing email {uid}: {e}")
    return len(messages)
