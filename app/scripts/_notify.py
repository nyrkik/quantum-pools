"""Shared notification helper.

Sends push notifications via ntfy (the QP ops notification channel on
http://localhost:7031, topic 'qp-alerts'). Used by health checks, the
inspection scraper, audit/QC scripts, and any other operational tooling
that needs to alert Brian on failure.

Always non-blocking — ntfy errors are logged but never raised. Cooldown
keys prevent the same recurring failure from spamming the channel.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

NTFY_URL = os.environ.get("NTFY_URL", "http://localhost:7031")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "qp-alerts")
DEFAULT_COOLDOWN_SECONDS = 1800  # 30 min


def _cooldown_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(" ", "_")
    return Path(f"/tmp/qp_notify_cooldown_{safe}")


def _should_send(key: str, cooldown: int) -> bool:
    p = _cooldown_path(key)
    if not p.exists():
        return True
    try:
        last = float(p.read_text().strip())
    except Exception:
        return True
    return (datetime.now().timestamp() - last) >= cooldown


def _mark_sent(key: str):
    try:
        _cooldown_path(key).write_text(str(datetime.now().timestamp()))
    except Exception:
        pass


def send_ntfy(
    title: str,
    body: str,
    *,
    priority: str = "default",
    tags: str | None = None,
    cooldown_key: str | None = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> bool:
    """Send a push notification via ntfy.

    Args:
        title: Short title (becomes the ntfy 'Title' header)
        body: Notification body text
        priority: ntfy priority — default, low, high, max, urgent
        tags: comma-separated emoji tags (e.g. 'warning', 'rotating_light')
        cooldown_key: if set, suppress repeats within `cooldown_seconds`
        cooldown_seconds: cooldown window if cooldown_key is set

    Returns True if sent, False if suppressed or failed.
    """
    if cooldown_key and not _should_send(cooldown_key, cooldown_seconds):
        logger.info(f"ntfy suppressed (cooldown): {title}")
        return False

    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags

    try:
        req = urllib.request.Request(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=body.encode(),
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        if cooldown_key:
            _mark_sent(cooldown_key)
        logger.info(f"ntfy sent: {title}")
        return True
    except Exception as e:
        logger.error(f"ntfy send failed: {e}")
        return False


def alert_failure(component: str, message: str, *, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS) -> bool:
    """Convenience: send a high-priority failure alert with a per-component cooldown."""
    return send_ntfy(
        title=f"QP {component} failure",
        body=message,
        priority="high",
        tags="warning",
        cooldown_key=f"failure_{component}",
        cooldown_seconds=cooldown_seconds,
    )
