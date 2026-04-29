"""Gmail Pub/Sub push: JWT verifier + webhook handler.

JWT verification is the security boundary — without it, anyone can POST
forged mailbox-change events to our public webhook. Most failure modes
have to map to specific exception types so the webhook returns 401 (not
silently 200) and we keep verification airtight.

The webhook itself accepts a wider set of "bad" inputs and returns 200
to drain the Pub/Sub retry queue (unknown account, missing fields,
sync-error). Idempotency comes from the existing email_uid dedup — a
duplicate push just hits a no-op pass through `_sync_history`.
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import patch

import pytest

from src.services.gmail.pubsub_verify import (
    PubSubVerifyError,
    verify_pubsub_jwt,
)


@pytest.mark.asyncio
async def test_verify_pubsub_jwt_rejects_empty_token():
    with pytest.raises(PubSubVerifyError, match="Missing bearer token"):
        verify_pubsub_jwt(
            "",
            expected_audience="https://example.com/push",
            expected_service_account="svc@project.iam.gserviceaccount.com",
        )


@pytest.mark.asyncio
async def test_verify_pubsub_jwt_signature_failure():
    """Garbage token → google-auth raises, we wrap as PubSubVerifyError."""
    with pytest.raises(PubSubVerifyError, match="JWT signature/audience invalid"):
        verify_pubsub_jwt(
            "not.a.real.jwt",
            expected_audience="https://example.com/push",
            expected_service_account="svc@project.iam.gserviceaccount.com",
        )


@pytest.mark.asyncio
async def test_verify_pubsub_jwt_wrong_issuer():
    """Mock past the signature check — make sure we still reject bad iss."""
    fake_claims = {
        "iss": "https://attacker.example.com",
        "email": "svc@project.iam.gserviceaccount.com",
        "email_verified": True,
    }
    with patch(
        "src.services.gmail.pubsub_verify.id_token.verify_oauth2_token",
        return_value=fake_claims,
    ):
        with pytest.raises(PubSubVerifyError, match="Unexpected issuer"):
            verify_pubsub_jwt(
                "any.jwt.token",
                expected_audience="https://example.com/push",
                expected_service_account="svc@project.iam.gserviceaccount.com",
            )


@pytest.mark.asyncio
async def test_verify_pubsub_jwt_wrong_service_account():
    """A valid JWT from a DIFFERENT subscription must be rejected — that's
    what stops a colocated GCP project from spoofing pushes at us."""
    fake_claims = {
        "iss": "https://accounts.google.com",
        "email": "evil@other-project.iam.gserviceaccount.com",
        "email_verified": True,
    }
    with patch(
        "src.services.gmail.pubsub_verify.id_token.verify_oauth2_token",
        return_value=fake_claims,
    ):
        with pytest.raises(PubSubVerifyError, match="Unexpected service-account email"):
            verify_pubsub_jwt(
                "any.jwt.token",
                expected_audience="https://example.com/push",
                expected_service_account="svc@project.iam.gserviceaccount.com",
            )


@pytest.mark.asyncio
async def test_verify_pubsub_jwt_email_not_verified():
    fake_claims = {
        "iss": "https://accounts.google.com",
        "email": "svc@project.iam.gserviceaccount.com",
        "email_verified": False,
    }
    with patch(
        "src.services.gmail.pubsub_verify.id_token.verify_oauth2_token",
        return_value=fake_claims,
    ):
        with pytest.raises(PubSubVerifyError, match="email_verified=false"):
            verify_pubsub_jwt(
                "any.jwt.token",
                expected_audience="https://example.com/push",
                expected_service_account="svc@project.iam.gserviceaccount.com",
            )


@pytest.mark.asyncio
async def test_verify_pubsub_jwt_happy_path():
    """All checks pass → returns the claims dict."""
    fake_claims = {
        "iss": "https://accounts.google.com",
        "email": "svc@project.iam.gserviceaccount.com",
        "email_verified": True,
        "aud": "https://example.com/push",
    }
    with patch(
        "src.services.gmail.pubsub_verify.id_token.verify_oauth2_token",
        return_value=fake_claims,
    ):
        out = verify_pubsub_jwt(
            "any.jwt.token",
            expected_audience="https://example.com/push",
            expected_service_account="svc@project.iam.gserviceaccount.com",
        )
    assert out == fake_claims


def _envelope(email_address: str, history_id: str) -> dict:
    """Build a Pub/Sub push envelope matching what Google delivers."""
    payload = json.dumps({"emailAddress": email_address, "historyId": history_id})
    data_b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return {
        "message": {
            "data": data_b64,
            "messageId": str(uuid.uuid4()),
            "publishTime": "2026-04-29T10:00:00.000Z",
        },
        "subscription": "projects/test-project/subscriptions/test-sub",
    }


@pytest.mark.asyncio
async def test_envelope_decoder_round_trip():
    """Sanity check our envelope helper matches Google's format — used by
    every webhook test below."""
    env = _envelope("brian@sapphire-pools.com", "12345")
    decoded = json.loads(base64.b64decode(env["message"]["data"]).decode("utf-8"))
    assert decoded == {"emailAddress": "brian@sapphire-pools.com", "historyId": "12345"}
