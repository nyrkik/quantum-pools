"""Gmail OAuth flow helpers.

Uses google-auth-oauthlib for the standard authorization-code flow:

    1. build_authorize_url(state, redirect_uri) → URL to redirect the user to
    2. user grants consent on Google
    3. Google redirects back to our callback with ?code=... &state=...
    4. exchange_code_for_tokens(code, redirect_uri) → access_token + refresh_token
    5. We store both in EmailIntegration.config_encrypted

When the access_token expires (1 hour), refresh_access_token(refresh_token)
mints a new one. Refresh tokens are long-lived (months) and only revoked by
the user disconnecting in Google Account settings.

Required env vars (set in app/.env):
    GOOGLE_OAUTH_CLIENT_ID
    GOOGLE_OAUTH_CLIENT_SECRET
    GOOGLE_OAUTH_REDIRECT_URI  (e.g. https://app.quantumpoolspro.com/api/v1/email-integrations/gmail/callback)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)

# Scopes we request. gmail.modify covers read + send + label manipulation.
# We do NOT request gmail.metadata (which only gives headers) — full body
# access is required for AI customer matching and case linking.
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


class OAuthConfigError(RuntimeError):
    """OAuth credentials are missing or invalid."""


def _client_config() -> dict:
    """Build the dict-format client config that google_auth_oauthlib expects.

    Reads GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET from env.
    Raises OAuthConfigError if either is missing.
    """
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise OAuthConfigError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set in .env. "
            "Create them at https://console.cloud.google.com/ → APIs & Services → Credentials → "
            "Create OAuth 2.0 Client ID (Web application)."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        }
    }


def build_authorize_url(state: str, redirect_uri: str) -> tuple[str, str]:
    """Build the Google consent URL for the user to visit.

    Args:
        state: Opaque CSRF token. We store this server-side and verify on
            callback (typically encodes the integration_id + a random nonce).
        redirect_uri: The exact URL Google will POST back to. Must match one
            of the Authorized redirect URIs configured in the OAuth client.

    Returns:
        (auth_url, code_verifier) — caller MUST persist the code_verifier
        alongside the state so it can be replayed during the token exchange
        (PKCE requirement). Without it, Google returns "Missing code verifier".
    """
    flow = Flow.from_client_config(
        _client_config(),
        scopes=OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",       # required to get a refresh_token
        include_granted_scopes="true",
        prompt="consent",            # always show consent screen so we re-receive refresh_token
        state=state,
    )
    # google_auth_oauthlib auto-generates a PKCE code_verifier inside
    # authorization_url(). We must replay it on token exchange.
    return auth_url, flow.code_verifier


def exchange_code_for_tokens(code: str, redirect_uri: str, code_verifier: str | None) -> dict[str, Any]:
    """Exchange the authorization code Google handed back for tokens.

    Args:
        code: The ?code=... value Google appended to our redirect URI.
        redirect_uri: Must match what we sent in build_authorize_url.
        code_verifier: The PKCE verifier captured from build_authorize_url.

    Returns a dict with: access_token, refresh_token, token_uri, client_id,
    client_secret, scopes, expiry_iso, account_email.
    """
    flow = Flow.from_client_config(
        _client_config(),
        scopes=OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds: Credentials = flow.credentials

    # Get the user's email address (the account they actually connected)
    account_email = ""
    try:
        from googleapiclient.discovery import build
        oauth2 = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = oauth2.userinfo().get().execute()
        account_email = info.get("email", "") or ""
    except Exception as e:
        logger.warning(f"Failed to fetch userinfo after token exchange: {e}")

    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
        "expiry_iso": creds.expiry.isoformat() if creds.expiry else None,
        "account_email": account_email,
    }


def refresh_access_token(token_payload: dict[str, Any]) -> dict[str, Any]:
    """Refresh an expired access_token using the stored refresh_token.

    Args:
        token_payload: dict from exchange_code_for_tokens (or a previous refresh).

    Returns:
        Updated token_payload with new access_token and expiry.
    """
    creds = Credentials(
        token=token_payload.get("access_token"),
        refresh_token=token_payload.get("refresh_token"),
        token_uri=token_payload.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=token_payload.get("client_id"),
        client_secret=token_payload.get("client_secret"),
        scopes=token_payload.get("scopes") or OAUTH_SCOPES,
    )
    creds.refresh(Request())

    updated = dict(token_payload)
    updated["access_token"] = creds.token
    updated["expiry_iso"] = creds.expiry.isoformat() if creds.expiry else None
    return updated
