"""AI Customer Support Agent — reads emails, drafts responses, SMS approval flow."""

import os
import re
import json
import email
import logging
import asyncio
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

import aiosmtplib
import anthropic
from imapclient import IMAPClient
from twilio.rest import Client as TwilioClient

from sqlalchemy import select
from src.core.database import get_db_context
from src.models.agent_message import AgentMessage

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
  "internal_note": "note for the team if any"
}

Guidelines:
- category "auto_reply" means no-reply addresses, bounce notifications, marketing — ignore these
- category "spam" — junk, ignore
- needs_approval = false ONLY for: simple acknowledgments, "we received your message", gate code confirmations where no action needed
- needs_approval = true for: schedule changes, complaints, billing questions, service requests, anything requiring a decision
- Draft responses should be warm, professional, concise. Sign as "Sapphire Pools" not a specific person.
- Never promise specific dates/times without approval
- If the email mentions a property name you recognize, include it in the response
- Keep responses under 3 sentences unless the situation requires more"""

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


async def classify_and_draft(from_email: str, subject: str, body: str) -> dict:
    """Use Claude to classify the email and draft a response."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    user_msg = f"From: {from_email}\nSubject: {subject}\n\n{body[:2000]}"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text
    # Parse JSON from response
    try:
        # Find JSON in response
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return {
        "category": "general",
        "urgency": "medium",
        "customer_name": None,
        "summary": subject,
        "needs_approval": True,
        "draft_response": "Thank you for reaching out. We'll get back to you shortly.",
        "internal_note": "Failed to parse AI response",
    }


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
            notes=result.get("internal_note"),
        )
        db.add(agent_msg)
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
            # Use the reply as instructions to redraft
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            redraft = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system="You write email responses for Sapphire Pools, a pool service company. Write a brief, professional response based on the instructions given. Sign as 'Sapphire Pools'. Keep it under 3 sentences.",
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
