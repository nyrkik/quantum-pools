"""Error Tracking Middleware — logs backend errors, alerts on repeated failures."""

import asyncio
import os
import time
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

logger = logging.getLogger(__name__)

# ── Error alerting ──────────────────────────────────────────────────
# Track 500s per endpoint. Alert after ALERT_THRESHOLD errors within
# WINDOW_SECONDS on the same endpoint. Cooldown prevents spam.

ALERT_THRESHOLD = 3
WINDOW_SECONDS = 300  # 5 minutes
COOLDOWN_SECONDS = 1800  # 30 min between alerts for the same endpoint


class _ErrorTracker:
    """In-process 500 tracker. Resets on restart — that's fine, restarts fix most issues."""

    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)  # endpoint → timestamps
        self._last_alert: dict[str, float] = {}  # endpoint → last alert time

    def record(self, endpoint: str) -> bool:
        """Record a 500. Returns True if alert threshold just crossed."""
        now = time.time()
        hits = self._hits[endpoint]
        # Prune old entries
        cutoff = now - WINDOW_SECONDS
        self._hits[endpoint] = [t for t in hits if t > cutoff]
        self._hits[endpoint].append(now)

        if len(self._hits[endpoint]) >= ALERT_THRESHOLD:
            last = self._last_alert.get(endpoint, 0)
            if now - last > COOLDOWN_SECONDS:
                self._last_alert[endpoint] = now
                return True
        return False


_tracker = _ErrorTracker()


async def _send_error_alert(endpoint: str, count: int, error_msg: str):
    """Send email alert for repeated 500s. Best-effort, never crashes."""
    try:
        from src.services.email_service import get_provider, EmailMessage
        notification_email = os.environ.get("NOTIFICATION_EMAIL")
        if not notification_email:
            logger.warning("NOTIFICATION_EMAIL not set — skipping error alert")
            return

        msg = EmailMessage(
            to=notification_email,
            subject=f"⚠ QuantumPools: {count} errors on {endpoint}",
            text_body=(
                f"Endpoint {endpoint} has hit {count} server errors "
                f"in the last {WINDOW_SECONDS // 60} minutes.\n\n"
                f"Latest error: {error_msg}\n\n"
                f"Check logs: sudo journalctl -u quantumpools-backend -f"
            ),
            from_email=os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com"),
            from_name="QuantumPools Monitor",
        )
        provider = get_provider()
        result = await provider.send(msg)
        if result.success:
            logger.info(f"Error alert sent for {endpoint}")
        else:
            logger.error(f"Failed to send error alert: {result.error}")
    except Exception as e:
        logger.error(f"Error alert failed: {e}")


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            if response.status_code >= 500:
                endpoint = f"{request.method} {request.url.path}"
                logger.error(f"HTTP {response.status_code} {endpoint}")
                if _tracker.record(endpoint):
                    count = len(_tracker._hits[endpoint])
                    asyncio.create_task(_send_error_alert(endpoint, count, f"HTTP {response.status_code}"))
            return response
        except Exception as exc:
            endpoint = f"{request.method} {request.url.path}"
            logger.error(f"Unhandled exception on {endpoint}: {exc}", exc_info=True)
            if _tracker.record(endpoint):
                count = len(_tracker._hits[endpoint])
                asyncio.create_task(_send_error_alert(endpoint, count, str(exc)))
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})
