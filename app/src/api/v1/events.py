"""Frontend event ingestion — POST /v1/events.

Receives batches of events emitted by the frontend `lib/events.ts` client.

Contract (see docs/ai-platform-phase-1.md §7.4):

- Auth required (cookie-based). Unauthenticated batches are rejected with 401.
- Rate limit: 100 requests per minute per session_id (or per IP if no session).
- Each event validated independently. Bad events are dropped from the batch
  but do NOT cause the batch to 500 — the receiver reports how many were
  accepted vs. rejected.
- Event-type allowlist: only events marked `frontend_emittable=True` in the
  event_catalog may be emitted from the frontend.
- Payload size cap (8KB) enforced per-event — oversized events are rejected.
- `client_emit_id` persisted for idempotency on retry.
- `created_at` is server-set (never trust client clocks — docs/event-taxonomy §7).

Events inherit the caller's `actor_user_id` / `organization_id` from the
authenticated context. Frontend cannot spoof these.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi.util import get_remote_address

from src.api.deps import get_current_org_user, OrgUserContext
from src.core.database import get_db
from src.core.rate_limiter import limiter
from src.services.events.event_catalog import EVENT_CATALOG, spec_for
from src.services.events.platform_event_service import (
    PAYLOAD_MAX_BYTES,
    Actor,
    PlatformEventService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

# Maximum events per batch request — protects against runaway clients.
MAX_BATCH_SIZE = 200


class EventIn(BaseModel):
    """Shape of a single event in an incoming batch."""

    event_type: str = Field(..., max_length=100)
    level: str = Field(..., max_length=20)
    entity_refs: dict = Field(default_factory=dict)
    payload: dict = Field(default_factory=dict)
    client_emit_id: Optional[str] = Field(default=None, max_length=36)


class EventBatch(BaseModel):
    events: list[EventIn] = Field(..., max_length=MAX_BATCH_SIZE)


class BatchResult(BaseModel):
    accepted: int
    rejected: int
    # Dropped-event reasons are logged server-side; clients don't get them
    # (avoid exposing catalog internals in a way that encourages scraping).


def _session_rate_key(request: Request) -> str:
    """Rate-limit key: X-Session-Id if present, fall back to remote address.

    Frontend client always sends X-Session-Id; absence indicates a direct
    / unauthorized caller and we fall back to per-IP limits.
    """
    sid = request.headers.get("X-Session-Id")
    if sid:
        return f"session:{sid}"
    return f"ip:{get_remote_address(request)}"


def _validate_event(ev: EventIn, org_id: Optional[str]) -> Optional[str]:
    """Return an error reason string if the event is invalid, None if OK."""
    spec = spec_for(ev.event_type)
    if spec is None:
        return "unknown_event_type"
    if not spec.frontend_emittable:
        return "not_frontend_emittable"
    if ev.level not in spec.levels:
        return "invalid_level_for_event"
    if spec.requires_org and not org_id:
        return "missing_org"

    # Frontend-allowed levels narrower than full enum — only user_action + error.
    # Prevents a malicious client from claiming system_action / agent_action.
    if ev.level not in ("user_action", "error"):
        return "forbidden_level_from_frontend"

    # Payload size pre-check. emit() also enforces but catching here avoids
    # the oversized-marker pollution from frontend-originated junk.
    import json
    try:
        serialized = json.dumps(ev.payload).encode("utf-8")
    except (TypeError, ValueError):
        return "non_serializable_payload"
    if len(serialized) > PAYLOAD_MAX_BYTES:
        return "payload_too_large"

    return None


@router.post("", response_model=BatchResult)
@limiter.limit("100/minute", key_func=_session_rate_key)
async def receive_events(
    request: Request,
    body: EventBatch,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a batch of frontend-emitted events.

    Each event is validated independently. Invalid events are dropped and
    logged; the batch still succeeds.
    """
    org_id = ctx.organization_id
    actor = Actor(
        actor_type="user",
        user_id=ctx.user.id,
    )

    session_id = request.headers.get("X-Session-Id")
    accepted = 0
    rejected = 0
    reasons: dict[str, int] = {}

    for ev in body.events:
        reason = _validate_event(ev, org_id)
        if reason is not None:
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue

        # The event_type's spec may declare requires_org=False (e.g., page.viewed
        # on an unauthenticated route in theory). For frontend POSTs we always
        # have an authenticated user, so org_id is always present here anyway.
        await PlatformEventService.emit(
            db=db,
            event_type=ev.event_type,
            level=ev.level,  # type: ignore[arg-type]
            actor=actor,
            organization_id=org_id,
            entity_refs=ev.entity_refs,
            payload=ev.payload,
            session_id=session_id,
            client_emit_id=ev.client_emit_id,
        )
        accepted += 1

    await db.commit()

    if rejected > 0:
        logger.warning(
            "Dropped %d events in batch from session=%s user=%s: %s",
            rejected,
            session_id,
            ctx.user.id,
            reasons,
        )

    return BatchResult(accepted=accepted, rejected=rejected)
