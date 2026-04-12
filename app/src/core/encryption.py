"""Symmetric encryption helper for sensitive at-rest data (OAuth tokens, etc.).

Uses Fernet (cryptography library, AES-128-CBC + HMAC-SHA256). Key is loaded
from the `EMAIL_INTEGRATION_KEY` environment variable. If not set in dev a
fixed dev key is used and a loud warning is logged — production MUST set
its own key.

Usage:
    from src.core.encryption import encrypt_dict, decrypt_dict

    cfg = {"oauth_token": "ya29.a0...", "refresh_token": "1//..."}
    encrypted_blob = encrypt_dict(cfg)         # str, safe to store in DB
    cfg_back = decrypt_dict(encrypted_blob)    # round-trip
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Loud, deterministic dev key — must be overridden in prod via env var.
# This is intentionally NOT a real secret because it ships in source.
# Production sets EMAIL_INTEGRATION_KEY in .env and the dev key is never used.
_DEV_KEY_FERNET = b"zuYWnSXLjMq_ggHFrERwObI_F3A1av3kea-iUy1tkkQ="


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = os.environ.get("EMAIL_INTEGRATION_KEY", "").strip()
    if not raw:
        logger.warning(
            "EMAIL_INTEGRATION_KEY not set — using a built-in DEV key. "
            "This is insecure for production. Generate a real key with "
            "`python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'` and put it in .env."
        )
        return Fernet(_DEV_KEY_FERNET)
    try:
        return Fernet(raw.encode())
    except Exception as e:
        raise RuntimeError(
            f"EMAIL_INTEGRATION_KEY is set but not a valid Fernet key: {e}"
        )


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string. Returns a base64 token safe to store in a TEXT column."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    """Decrypt a token previously produced by encrypt_str. Raises on tamper."""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError(f"Decryption failed (key mismatch or tampered data): {e}")


def encrypt_dict(d: dict) -> str:
    """Convenience: JSON-serialize then encrypt."""
    return encrypt_str(json.dumps(d, sort_keys=True))


def decrypt_dict(token: str) -> dict:
    """Convenience: decrypt then JSON-deserialize."""
    return json.loads(decrypt_str(token))
