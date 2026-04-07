"""Sending emails and SMS."""

import os
import logging

from twilio.rest import Client as TwilioClient

logger = logging.getLogger(__name__)

# Config from env
FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")
FROM_NAME = os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
APPROVAL_NUMBERS = [n.strip() for n in os.environ.get("AGENT_APPROVAL_NUMBERS", "").split(",") if n.strip()]


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
    from .orchestrator import _pending_approvals

    # Truncate for SMS (160 char limit per segment)
    text = f"\U0001f4e7 {from_email}\n{summary}\n\nDraft: \"{draft[:200]}\"\n\nReply OK to send, or reply with changes.\nRef: {agent_msg_id[:8]}"

    _pending_approvals[agent_msg_id[:8]] = agent_msg_id

    for number in APPROVAL_NUMBERS:
        await send_sms(number, text)


async def send_email_response(to: str, subject: str, body: str):
    """Send email reply via best available provider (Postmark or SMTP fallback)."""
    from src.services.email_service import EmailMessage, EmailResult, get_provider

    re_subject = f"Re: {subject}" if subject and not subject.startswith("Re:") else subject
    msg = EmailMessage(
        to=to,
        subject=re_subject,
        text_body=body,
        from_email=FROM_EMAIL,
        from_name=FROM_NAME,
    )

    try:
        provider = get_provider()
        result = await provider.send(msg)
        if result.success:
            logger.info(f"Email sent to {to}: {subject} (id={result.message_id})")
            return result
        else:
            logger.error(f"Failed to send email to {to}: {result.error}")
            return None
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return None


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
            await send_sms(number, f"\u2705 {approver_name} handled: {summary[:100]}")
