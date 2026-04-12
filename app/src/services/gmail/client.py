"""Authenticated Gmail API client builder.

Wraps `googleapiclient.discovery.build()` and handles automatic refresh of
the access_token using the stored refresh_token. Also persists the refreshed
token back into the EmailIntegration row.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.models.email_integration import EmailIntegration
from src.services.gmail.oauth import OAUTH_SCOPES

logger = logging.getLogger(__name__)


class GmailClientError(RuntimeError):
    """Raised when the Gmail client cannot be built or a call fails fatally."""


def _build_credentials(token_payload: dict[str, Any]) -> Credentials:
    """Construct a google-auth Credentials object from our stored token dict."""
    expiry = None
    if token_payload.get("expiry_iso"):
        try:
            expiry = datetime.fromisoformat(token_payload["expiry_iso"])
            # google-auth expects naive UTC datetimes for expiry
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except Exception:
            expiry = None

    return Credentials(
        token=token_payload.get("access_token"),
        refresh_token=token_payload.get("refresh_token"),
        token_uri=token_payload.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=token_payload.get("client_id"),
        client_secret=token_payload.get("client_secret"),
        scopes=token_payload.get("scopes") or OAUTH_SCOPES,
        expiry=expiry,
    )


def build_gmail_client(integration: EmailIntegration, db_session=None):
    """Build an authenticated Gmail API client for this integration.

    Refreshes the access_token if it's expired and persists the new token
    back into the integration row (if a db_session is provided so we can flush).

    Args:
        integration: The EmailIntegration row (must be type='gmail_api',
            status='connected', config containing OAuth tokens).
        db_session: Optional async DB session — used to persist refreshed tokens.

    Returns:
        A `googleapiclient.discovery.Resource` for the Gmail API
        ('gmail', 'v1'). Caller uses `.users().messages()...` etc.

    Raises:
        GmailClientError: if the integration isn't gmail_api or has no tokens.
    """
    if integration.type != "gmail_api":
        raise GmailClientError(f"integration {integration.id} is not gmail_api")

    config = integration.get_config()
    if not config.get("access_token") and not config.get("refresh_token"):
        raise GmailClientError(
            f"integration {integration.id} has no OAuth tokens — needs (re)connect"
        )

    creds = _build_credentials(config)

    # Refresh if expired (or no expiry recorded)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Persist the new token back into the integration
                config["access_token"] = creds.token
                config["expiry_iso"] = creds.expiry.isoformat() if creds.expiry else None
                integration.set_config(config)
                logger.info(f"Refreshed Gmail access_token for integration {integration.id}")
            except Exception as e:
                raise GmailClientError(f"Token refresh failed: {e}") from e
        else:
            raise GmailClientError(
                f"integration {integration.id} credentials invalid and no refresh_token"
            )

    return build("gmail", "v1", credentials=creds, cache_discovery=False)
