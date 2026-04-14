"""Email integration management — list, OAuth (Gmail), disconnect, sync.

Phase 5b.1/5b.2 of docs/email-integrations-plan.md.

Routes:
    GET    /v1/email-integrations               — list this org's integrations
    GET    /v1/email-integrations/{id}          — single integration detail
    POST   /v1/email-integrations/gmail/authorize  — start Gmail OAuth flow
    GET    /v1/email-integrations/gmail/callback   — OAuth callback (Google)
    POST   /v1/email-integrations/{id}/sync     — manually trigger initial/incremental sync
    DELETE /v1/email-integrations/{id}          — disconnect

The OAuth callback is exposed publicly (no auth) because Google redirects
the user's browser to it directly. CSRF is prevented by the `state`
parameter, which we generate as `<integration_id>:<random_nonce>` and
verify on callback.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_org_user, get_db, OrgUserContext
from src.models.email_integration import EmailIntegration, IntegrationType, IntegrationStatus
from src.models.organization import Organization

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email-integrations", tags=["email-integrations"])


# In-memory CSRF state store. State strings expire after 10 minutes.
# OK because the OAuth flow is short-lived. For multi-process deployments,
# move this into Redis.
_PENDING_OAUTH: dict[str, dict] = {}
_OAUTH_TTL_SECONDS = 600


def _redirect_uri() -> str:
    """The exact URI Google will POST back to. Must match the Authorized
    redirect URIs in the Google Cloud OAuth client configuration.
    """
    explicit = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("APP_BASE_URL", "https://app.quantumpoolspro.com").rstrip("/")
    return f"{base}/api/v1/email-integrations/gmail/callback"


def _to_response(ei: EmailIntegration) -> dict:
    """Sanitized response — never returns config_encrypted or token contents."""
    return {
        "id": ei.id,
        "type": ei.type,
        "status": ei.status,
        "account_email": ei.account_email,
        "inbound_sender_address": ei.inbound_sender_address,
        "outbound_provider": ei.outbound_provider,
        "is_primary": ei.is_primary,
        "last_sync_at": ei.last_sync_at.isoformat() if ei.last_sync_at else None,
        "last_error": ei.last_error,
        "last_error_at": ei.last_error_at.isoformat() if ei.last_error_at else None,
        "created_at": ei.created_at.isoformat() if ei.created_at else None,
    }


@router.get("")
async def list_integrations(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all email integrations for the current org."""
    rows = (await db.execute(
        select(EmailIntegration)
        .where(EmailIntegration.organization_id == ctx.organization_id)
        .order_by(EmailIntegration.is_primary.desc(), EmailIntegration.created_at)
    )).scalars().all()
    return {"integrations": [_to_response(r) for r in rows]}


@router.get("/settings")
async def get_email_settings(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get org-level email settings."""
    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one()
    return {"email_auto_send_enabled": org.email_auto_send_enabled}


class EmailSettingsBody(BaseModel):
    email_auto_send_enabled: bool


@router.put("/settings")
async def update_email_settings(
    body: EmailSettingsBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Update org-level email settings. Owner/admin only."""
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owner or admin can change email settings")
    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one()
    org.email_auto_send_enabled = body.email_auto_send_enabled
    await db.commit()
    return {"email_auto_send_enabled": org.email_auto_send_enabled}


@router.get("/{integration_id}")
async def get_integration(
    integration_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(EmailIntegration).where(
            EmailIntegration.id == integration_id,
            EmailIntegration.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Integration not found")
    return _to_response(row)


class GmailAuthorizeBody(BaseModel):
    # Future: support multi-account by passing an existing integration_id to
    # re-auth, or omit to create a new one. For now we always create a new
    # integration row in 'connecting' state.
    pass


@router.post("/gmail/authorize")
async def gmail_authorize(
    body: GmailAuthorizeBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Start the Gmail OAuth flow. Returns the URL the browser should redirect to."""
    from src.services.gmail.oauth import build_authorize_url, OAuthConfigError

    # Create a placeholder EmailIntegration in 'connecting' state.
    # On callback we'll update it with tokens and flip status to 'connected'.
    integration = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        type=IntegrationType.gmail_api.value,
        status=IntegrationStatus.connecting.value,
        outbound_provider="gmail_api",
        is_primary=False,  # set to True only after first successful sync if no other primary exists
    )
    db.add(integration)
    await db.commit()

    # CSRF state — opaque to Google, validated on callback
    nonce = secrets.token_urlsafe(16)
    state = f"{integration.id}:{nonce}"
    _PENDING_OAUTH[state] = {
        "integration_id": integration.id,
        "org_id": ctx.organization_id,
        "user_id": ctx.user.id,
        "created_at": datetime.now(timezone.utc).timestamp(),
    }

    try:
        url, code_verifier = build_authorize_url(state=state, redirect_uri=_redirect_uri())
    except OAuthConfigError as e:
        # Roll back the placeholder integration
        await db.delete(integration)
        await db.commit()
        raise HTTPException(503, str(e))

    _PENDING_OAUTH[state]["code_verifier"] = code_verifier
    return {"authorize_url": url, "integration_id": integration.id}


@router.get("/gmail/callback")
async def gmail_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Google's redirect destination after the user grants/denies consent.

    No auth dependency — Google sends the user's browser here directly. CSRF
    is prevented by the `state` parameter (must match what we issued in
    /authorize).

    Returns a redirect to the frontend Settings → Email page with a status
    query param so the UI can show success/failure.
    """
    frontend_base = os.environ.get("APP_BASE_URL", "https://app.quantumpoolspro.com").rstrip("/")
    settings_url = f"{frontend_base}/settings/email"

    if error:
        logger.warning(f"Gmail OAuth user denied / error: {error}")
        return RedirectResponse(f"{settings_url}?gmail=error&reason={error}")

    if not code or not state:
        return RedirectResponse(f"{settings_url}?gmail=error&reason=missing_params")

    pending = _PENDING_OAUTH.pop(state, None)
    if not pending:
        return RedirectResponse(f"{settings_url}?gmail=error&reason=invalid_state")

    if (datetime.now(timezone.utc).timestamp() - pending["created_at"]) > _OAUTH_TTL_SECONDS:
        return RedirectResponse(f"{settings_url}?gmail=error&reason=state_expired")

    integration_id = pending["integration_id"]
    integration = (await db.execute(
        select(EmailIntegration).where(EmailIntegration.id == integration_id)
    )).scalar_one_or_none()
    if not integration:
        return RedirectResponse(f"{settings_url}?gmail=error&reason=integration_missing")

    # Exchange the code for tokens (replaying the PKCE code_verifier we stashed)
    from src.services.gmail.oauth import exchange_code_for_tokens
    try:
        token_payload = exchange_code_for_tokens(
            code, _redirect_uri(), pending.get("code_verifier")
        )
    except Exception as e:
        logger.error(f"Token exchange failed: {e}", exc_info=True)
        integration.status = IntegrationStatus.error.value
        integration.last_error = f"OAuth code exchange failed: {e}"
        integration.last_error_at = datetime.now(timezone.utc)
        await db.commit()
        return RedirectResponse(f"{settings_url}?gmail=error&reason=token_exchange_failed")

    integration.account_email = token_payload.get("account_email") or None
    integration.set_config(token_payload)
    integration.status = IntegrationStatus.connected.value
    integration.last_error = None
    integration.last_error_at = None

    # Promote this Gmail integration to primary for the org. Gmail-mode takes
    # precedence over managed-mode (Postmark fallback) — when a user OAuths
    # in their own mailbox, they expect outbound to flow through it. Demote
    # any existing primary rows (across all types) so "primary" stays unique.
    await db.execute(
        EmailIntegration.__table__.update()
        .where(
            EmailIntegration.organization_id == integration.organization_id,
            EmailIntegration.id != integration.id,
            EmailIntegration.is_primary == True,  # noqa: E712
        )
        .values(is_primary=False)
    )
    integration.is_primary = True

    await db.commit()
    logger.info(f"Gmail OAuth connected: integration={integration.id} account={integration.account_email}")

    return RedirectResponse(f"{settings_url}?gmail=connected&account={integration.account_email or ''}")


@router.post("/{integration_id}/sync")
async def trigger_sync(
    integration_id: str,
    days: int = Query(30, ge=1, le=365),
    incremental: bool = Query(False),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an initial or incremental sync for a Gmail-mode integration."""
    integration = (await db.execute(
        select(EmailIntegration).where(
            EmailIntegration.id == integration_id,
            EmailIntegration.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not integration:
        raise HTTPException(404, "Integration not found")
    if integration.type != IntegrationType.gmail_api.value:
        raise HTTPException(400, f"Sync only supported for gmail_api, not {integration.type}")
    if integration.status != IntegrationStatus.connected.value:
        raise HTTPException(400, f"Integration is {integration.status}, not connected")

    from src.services.gmail.sync import GmailSyncService
    svc = GmailSyncService(integration)
    try:
        if incremental:
            stats = await svc.incremental_sync()
        else:
            stats = await svc.initial_sync(days=days)
    except Exception as e:
        logger.error(f"Gmail sync failed for integration {integration_id}: {e}", exc_info=True)
        integration.status = IntegrationStatus.error.value
        integration.last_error = str(e)[:1000]
        integration.last_error_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(500, f"Sync failed: {e}")

    return {"stats": stats, "integration": _to_response(integration)}


@router.post("/sync-all")
async def sync_all(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger incremental sync for all connected Gmail integrations in the org.

    Used by the inbox refresh button. Returns aggregate stats.
    """
    integrations = (await db.execute(
        select(EmailIntegration).where(
            EmailIntegration.organization_id == ctx.organization_id,
            EmailIntegration.type == IntegrationType.gmail_api.value,
            EmailIntegration.status == IntegrationStatus.connected.value,
        )
    )).scalars().all()

    if not integrations:
        return {"synced": 0, "stats": {"fetched": 0, "ingested": 0, "skipped": 0, "errors": 0}}

    from src.services.gmail.sync import GmailSyncService
    total = {"fetched": 0, "ingested": 0, "skipped": 0, "errors": 0}
    synced = 0
    for integration in integrations:
        try:
            svc = GmailSyncService(integration)
            stats = await svc.incremental_sync()
            for k in total:
                total[k] += stats.get(k, 0)
            synced += 1
        except Exception as e:
            logger.warning(f"sync-all: integration {integration.id} failed: {e}")
            total["errors"] += 1

    return {"synced": synced, "stats": total}


@router.delete("/{integration_id}")
async def disconnect_integration(
    integration_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect an integration — hard delete the row. Past synced
    AgentMessages are not touched (they're customer email history, not
    integration state). Reconnecting later creates a fresh row.
    """
    integration = (await db.execute(
        select(EmailIntegration).where(
            EmailIntegration.id == integration_id,
            EmailIntegration.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not integration:
        raise HTTPException(404, "Integration not found")

    await db.delete(integration)
    await db.commit()
    return {"ok": True}


