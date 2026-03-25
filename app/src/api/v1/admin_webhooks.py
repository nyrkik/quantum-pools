"""Admin webhook endpoints — Twilio SMS."""

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/admin", tags=["admin-webhooks"])


@router.post("/twilio-webhook")
async def twilio_sms_webhook(request: Request):
    """Handle incoming SMS from Twilio (approval replies)."""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "")

    if from_number and body:
        from src.services.customer_agent import handle_sms_reply
        import asyncio
        asyncio.create_task(handle_sms_reply(from_number, body))

    # Return empty TwiML to acknowledge
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
