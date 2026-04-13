"""Admin webhook endpoints — Twilio SMS + Postmark delivery events."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin-webhooks"])


@router.post("/postmark-webhook")
async def postmark_delivery_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Postmark delivery/bounce/open webhooks.

    Postmark sends one POST per event. RecordType tells us what it is:
    - Delivery — email delivered
    - Bounce — email bounced
    - Open — recipient opened the email
    - SpamComplaint — recipient marked spam

    We match by MessageID to update the AgentMessage.
    """
    from src.models.agent_message import AgentMessage

    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid json"}

    record_type = payload.get("RecordType", "")
    message_id = payload.get("MessageID") or payload.get("MessageId")
    if not message_id:
        return {"ok": True, "skipped": "no message id"}

    msg = (await db.execute(
        select(AgentMessage).where(AgentMessage.postmark_message_id == message_id)
    )).scalar_one_or_none()
    if not msg:
        logger.info(f"Postmark webhook for unknown MessageID {message_id} ({record_type})")
        return {"ok": True, "skipped": "unknown message"}

    now = datetime.now(timezone.utc)

    if record_type == "Delivery":
        msg.delivery_status = "delivered"
        msg.delivered_at = now
    elif record_type == "Bounce":
        msg.delivery_status = "bounced"
        msg.delivery_error = payload.get("Description") or payload.get("Type") or "bounced"
        logger.warning(f"Bounce for {msg.to_email}: {msg.delivery_error}")
    elif record_type == "Open":
        msg.open_count = (msg.open_count or 0) + 1
        if not msg.first_opened_at:
            msg.first_opened_at = now
        if msg.delivery_status not in ("bounced", "spam_complaint"):
            msg.delivery_status = "opened"
    elif record_type == "SpamComplaint":
        msg.delivery_status = "spam_complaint"
        msg.delivery_error = "Recipient marked as spam"
        logger.warning(f"Spam complaint for {msg.to_email}")

    await db.commit()
    return {"ok": True}


@router.post("/twilio-webhook")
async def twilio_sms_webhook(request: Request):
    """Handle incoming SMS from Twilio (approval replies)."""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "")

    if from_number and body:
        from src.services.agents.orchestrator import handle_sms_reply
        import asyncio
        asyncio.create_task(handle_sms_reply(from_number, body))

    # Return empty TwiML to acknowledge
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
