"""Webhook signature validation — guards C3/H3 from the security audit.

If any of these fail, the public-internet attack surface (anyone forging
delivery events / inbound emails) has reopened.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _fake_request(headers: dict[str, str]) -> Request:
    """Build a minimal Starlette Request with the given headers — enough for
    the verifier, which only reads from request.headers and request.client."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/admin/postmark-webhook",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 5555),
    }
    return Request(scope)


def test_webhook_token_missing_header_rejects():
    """No X-Webhook-Token header → 401."""
    from src.api.v1.admin_webhooks import verify_postmark_webhook_token
    req = _fake_request({})
    with pytest.raises(HTTPException) as exc:
        verify_postmark_webhook_token(req)
    assert exc.value.status_code == 401


def test_webhook_token_wrong_value_rejects():
    """Wrong X-Webhook-Token → 401."""
    from src.api.v1.admin_webhooks import verify_postmark_webhook_token
    req = _fake_request({"X-Webhook-Token": "wrong-token"})
    with pytest.raises(HTTPException) as exc:
        verify_postmark_webhook_token(req)
    assert exc.value.status_code == 401


def test_webhook_token_correct_passes():
    """Correct X-Webhook-Token → no exception."""
    from src.api.v1.admin_webhooks import verify_postmark_webhook_token
    req = _fake_request({"X-Webhook-Token": "test-webhook-token-for-pytest"})
    verify_postmark_webhook_token(req)  # raises HTTPException on failure


def test_webhook_token_empty_env_fails_closed(monkeypatch):
    """If POSTMARK_WEBHOOK_TOKEN env var is unset → 503 (fail-closed).

    This is the most important guard: deploying without the env var must NOT
    silently let through unauthenticated webhooks.
    """
    monkeypatch.delenv("POSTMARK_WEBHOOK_TOKEN", raising=False)
    from src.api.v1.admin_webhooks import verify_postmark_webhook_token
    req = _fake_request({"X-Webhook-Token": "anything"})
    with pytest.raises(HTTPException) as exc:
        verify_postmark_webhook_token(req)
    assert exc.value.status_code == 503


def test_webhook_token_constant_time_compare():
    """secrets.compare_digest is used (constant-time) to prevent timing
    oracle attacks. We can't prove timing here, but we can verify the
    function imports + uses secrets.compare_digest correctly."""
    import inspect
    from src.api.v1 import admin_webhooks
    src = inspect.getsource(admin_webhooks.verify_postmark_webhook_token)
    assert "compare_digest" in src, (
        "verify_postmark_webhook_token must use secrets.compare_digest — "
        "plain `==` comparison is vulnerable to timing attacks."
    )
