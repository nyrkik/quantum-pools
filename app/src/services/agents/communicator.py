"""Sending customer-facing email.

SMS urgency alerts (Twilio) lived here until 2026-04-24; removed in Phase 5
Step 5 follow-up. The SMS-approve-to-send flow that motivated them was
retired when auto-send was (2026-04-14), and by this date every reference
to the SMS helpers had become orphaned — see the commit message for full
history. If the team ever wants urgency pings again, ntfy on MS-01:7031
is the right layer (already in the infra).
"""

import os
import logging

logger = logging.getLogger(__name__)

# Config from env
FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")
FROM_NAME = os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")


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
