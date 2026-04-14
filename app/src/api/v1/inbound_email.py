"""Inbound email webhook — public endpoint for email providers."""

import logging
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.database import get_db
from src.core.rate_limiter import limiter
from src.services.inbound_email_service import InboundEmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbound-email", tags=["inbound-email"])

_service = InboundEmailService()

VALID_PROVIDERS = {"sendgrid", "postmark", "mailgun", "cloudflare", "generic"}


@router.post("/webhook/{org_slug}")
@limiter.limit("30/minute")
async def receive_webhook(
    org_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    provider: str = "generic",
    type: str | None = None,
):
    """Receive inbound email from an email provider webhook.

    Authenticated via shared `X-Webhook-Token` header against the
    POSTMARK_WEBHOOK_TOKEN env var. This is the same secret used for the
    delivery webhook; configure both webhooks in the Postmark dashboard with
    the custom header.

    Security:
    - Rate limited to 30/minute per IP
    - X-Webhook-Token shared secret (fail-closed if env var unset)
    - Org slug must exist and be active
    - Block rules applied before processing

    Query params:
        provider: sendgrid | postmark | mailgun | generic (default: generic)
        type: bounce | delivery (optional — for status webhooks)
    """
    # Reuse the verifier from admin_webhooks — same shared secret, same env var.
    from src.api.v1.admin_webhooks import verify_postmark_webhook_token
    verify_postmark_webhook_token(request)

    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Parse body — handle both JSON and form-encoded (SendGrid uses form)
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        payload = dict(form)
    else:
        # Try JSON first, fall back to raw body
        try:
            payload = await request.json()
        except Exception:
            body = await request.body()
            payload = {"raw": body.decode("utf-8", errors="replace")}

    result = await _service.process_webhook(
        db, org_slug, payload, provider=provider, webhook_type=type,
    )

    if result.get("status") == "error" and result.get("detail") == "Organization not found":
        raise HTTPException(status_code=404, detail="Organization not found")

    # Real-time events are published from the orchestrator after processing

    # Always return 200 to email providers (they retry on non-2xx)
    return result


@router.head("/webhook/{org_slug}")
async def webhook_health(org_slug: str):
    """Health check for email provider webhook validation.

    Some providers (SendGrid, Postmark) send a HEAD or GET request
    to verify the webhook URL exists before activating it.
    """
    return {"ok": True}
