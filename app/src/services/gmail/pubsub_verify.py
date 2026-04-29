"""Verify the Bearer JWT on incoming Gmail Pub/Sub pushes.

Pub/Sub push subscriptions sign every request with a Google-issued JWT
in the Authorization header (when configured with an OIDC service-
account identity). Verifying the signature, audience, issuer, and
the email claim is what stops a malicious actor from POSTing forged
mailbox-change events to our public webhook.

Standard verification recipe:
- Issuer: `accounts.google.com` or `https://accounts.google.com`
- Audience: the URL we configured on the Pub/Sub subscription
- email claim: must equal the service account that owns the push sub
- email_verified: true
- Signature: validated against Google's public JWKs

`google.oauth2.id_token.verify_oauth2_token` covers signature + iss
+ aud + exp. We layer the email-claim check on top.
"""

from __future__ import annotations

import logging
from typing import Any

from google.auth.transport import requests as g_requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)


class PubSubVerifyError(Exception):
    """Raised when a Pub/Sub push JWT fails verification."""


# Lazy-init the Request transport so we don't create a new HTTP session
# per request. google-auth keeps a small cert cache on this instance.
_request_transport: g_requests.Request | None = None


def _get_transport() -> g_requests.Request:
    global _request_transport
    if _request_transport is None:
        _request_transport = g_requests.Request()
    return _request_transport


def verify_pubsub_jwt(
    bearer_token: str,
    *,
    expected_audience: str,
    expected_service_account: str,
) -> dict[str, Any]:
    """Verify a Pub/Sub push Bearer token.

    Args:
        bearer_token: the JWT (without the "Bearer " prefix).
        expected_audience: the URL the push subscription was configured with.
            Mismatch → reject. Tells us the push was actually targeted at us.
        expected_service_account: the email of the service account that owns
            the push subscription. Mismatch → reject. Tells us the push
            actually came from our subscription, not someone else's.

    Returns:
        The decoded claims dict on success.

    Raises:
        PubSubVerifyError on any failure (signature, audience, issuer,
        service-account email, or expiry).
    """
    if not bearer_token:
        raise PubSubVerifyError("Missing bearer token")

    try:
        claims = id_token.verify_oauth2_token(
            bearer_token,
            _get_transport(),
            audience=expected_audience,
        )
    except Exception as e:
        raise PubSubVerifyError(f"JWT signature/audience invalid: {e}") from e

    issuer = claims.get("iss")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        raise PubSubVerifyError(f"Unexpected issuer: {issuer!r}")

    email = claims.get("email")
    if email != expected_service_account:
        raise PubSubVerifyError(
            f"Unexpected service-account email: {email!r} "
            f"(expected {expected_service_account!r})"
        )
    if not claims.get("email_verified"):
        raise PubSubVerifyError("email_verified=false")

    return claims
