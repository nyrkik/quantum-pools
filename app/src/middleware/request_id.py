"""Request ID middleware — generates/propagates a UUID4 per HTTP request.

Every authenticated or anonymous request gets a `request_id` attached to:
  - `request.state.request_id` — accessible anywhere in the request chain
  - a ContextVar read by `PlatformEventService.emit()` for auto-propagation
  - the `X-Request-ID` response header — lets clients correlate

If the client sends an `X-Request-ID` header, we honor it (future: useful
when the frontend wants cross-surface correlation). Otherwise we generate.

Design reference: docs/ai-platform-phase-1.md §5.2.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.services.events.platform_event_service import (
    set_request_id,
    reset_request_id,
    set_session_id,
    reset_session_id,
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request_id to every request. Also picks up the frontend's
    `X-Session-Id` and propagates via contextvar so emit() can use it."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Request ID — honor client-supplied or generate.
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        rid_token = set_request_id(rid)

        # 2. Session ID — frontend-originated; empty for backend-internal requests.
        sid = request.headers.get("X-Session-Id")
        request.state.session_id = sid
        sid_token = set_session_id(sid) if sid else None

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            reset_request_id(rid_token)
            if sid_token is not None:
                reset_session_id(sid_token)
