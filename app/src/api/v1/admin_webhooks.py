"""Admin webhook endpoints — Twilio SMS + Postmark delivery events."""

import logging
import os
import secrets as _secrets
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.rate_limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin-webhooks"])


def verify_postmark_webhook_token(request: Request) -> None:
    """Validate the X-Webhook-Token header against POSTMARK_WEBHOOK_TOKEN env var.

    Postmark doesn't ship native HMAC signatures, but their dashboard lets you
    attach custom headers to outbound webhooks. We require a shared secret in
    `X-Webhook-Token`. Constant-time compare to avoid timing oracles.

    FAIL CLOSED: if the env var isn't configured, every webhook is rejected
    with 503. Better to lose delivery events than to silently accept forged
    ones from the public internet.

    Why this matters: before this check, anyone on the internet could POST to
    /api/v1/admin/postmark-webhook with `{"RecordType":"Bounce","MessageID":"<id>"}`
    and mark any outbound email in the DB as bounced.
    """
    expected = os.environ.get("POSTMARK_WEBHOOK_TOKEN")
    if not expected:
        logger.error(
            "POSTMARK_WEBHOOK_TOKEN not set — rejecting webhook (fail-closed). "
            "Set it in .env and configure Postmark to send X-Webhook-Token header."
        )
        raise HTTPException(status_code=503, detail="Webhook auth not configured")

    provided = request.headers.get("X-Webhook-Token", "")
    if not _secrets.compare_digest(provided, expected):
        logger.warning(
            f"Postmark webhook rejected: bad/missing X-Webhook-Token "
            f"(remote={request.client.host if request.client else 'unknown'})"
        )
        raise HTTPException(status_code=401, detail="Invalid webhook token")


@router.post("/postmark-webhook")
@limiter.limit("600/minute")
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
    verify_postmark_webhook_token(request)
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
    """Twilio SMS webhook — kept so replies to outbound SMS urgency pings
    don't 404 on Twilio's side. The pre-Phase-5 SMS approve-via-text flow
    (`handle_sms_reply`) was retired when drafts migrated to the proposal
    system; replies now are ack-only. Approvals happen in the inbox UI via
    ProposalCard. DNA rule 5 — AI never commits to the customer."""
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
