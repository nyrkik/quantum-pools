"""Platform event emission — the single entrypoint for writing to
`platform_events`.

Design contract (see docs/ai-platform-phase-1.md §5.1, docs/event-taxonomy.md):

- Non-blocking: `emit()` never raises and never blocks the caller on failure.
- Transactional: writes inside the caller's session. If the business
  transaction rolls back, the event rolls back too (correct — don't record
  actions that didn't commit).
- Fail-soft: DB/serialization errors are logged and swallowed.
- Idempotent: when `client_emit_id` is supplied, a check-then-insert
  prevents duplicates. (Partitioned tables can't have unique indexes
  excluding the partition key, so idempotency is enforced in app code.)
- Payload capped at 8KB. Oversized payloads are truncated to a marker
  and a separate `platform_event.oversized_payload` event is recorded.
- Context propagation: `request_id` / `session_id` / `job_run_id` are
  pulled from contextvars set by middleware / job-run context manager.

Do not write to `platform_events` from anywhere else.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime  # noqa: F401 — referenced as forward-ref in emit signature
from typing import Literal, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PAYLOAD_MAX_BYTES = 8 * 1024

Level = Literal["user_action", "system_action", "agent_action", "error"]
ActorType = Literal["user", "system", "agent"]


# ---------------------------------------------------------------------------
# Context variables — populated by middleware and job_run_context manager.
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[Optional[str]] = ContextVar("pe_request_id", default=None)
_session_id_var: ContextVar[Optional[str]] = ContextVar("pe_session_id", default=None)
_job_run_id_var: ContextVar[Optional[str]] = ContextVar("pe_job_run_id", default=None)


def _current_request_id() -> Optional[str]:
    return _request_id_var.get()


def _current_session_id() -> Optional[str]:
    return _session_id_var.get()


def _current_job_run_id() -> Optional[str]:
    return _job_run_id_var.get()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Actor:
    """Who the emission is attributed to."""
    actor_type: ActorType = "user"
    user_id: Optional[str] = None
    acting_as_user_id: Optional[str] = None
    view_as_role: Optional[str] = None
    actor_agent_type: Optional[str] = None  # set when actor_type='agent'


def actor_system() -> Actor:
    return Actor(actor_type="system")


def actor_agent(agent_type: str) -> Actor:
    return Actor(actor_type="agent", actor_agent_type=agent_type)


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


class PlatformEventService:
    """Primary emission surface. All events flow through here."""

    @staticmethod
    async def emit(
        db: AsyncSession,
        event_type: str,
        level: Level,
        actor: Actor,
        *,
        organization_id: Optional[str] = None,
        entity_refs: Optional[dict] = None,
        payload: Optional[dict] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        job_run_id: Optional[str] = None,
        client_emit_id: Optional[str] = None,
        created_at: Optional["datetime"] = None,
    ) -> None:
        """Emit an event. Never raises; never blocks.

        Args:
            db: caller's session — event writes share the caller's transaction.
            event_type: from docs/event-taxonomy.md. Dotted naming.
            level: analytic category.
            actor: who did it.
            organization_id: scope. Null only for platform-level events
                (login attempts pre-auth, signup).
            entity_refs: polymorphic `{entity_name: id}` map.
            payload: event-specific fields. No PII. Capped at 8KB.
            request_id / session_id / job_run_id: correlation. Auto-read
                from contextvars if not supplied.
            client_emit_id: idempotency key. Deduped before insert.
            created_at: overrides the default NOW() timestamp. Intended
                for backfill/migration scripts replaying historical events.
                Never use this for live-emitted events — always pass None
                for those so the server clock is authoritative.
        """
        try:
            payload_obj = payload or {}
            entity_refs_obj = entity_refs or {}

            # 1. Size cap + truncation.
            serialized_payload = json.dumps(payload_obj).encode("utf-8")
            if len(serialized_payload) > PAYLOAD_MAX_BYTES:
                attempted = len(serialized_payload)
                payload_obj = {
                    "__oversized__": True,
                    "original_size_bytes": attempted,
                }
                serialized_payload = json.dumps(payload_obj).encode("utf-8")
                # Fire an oversized-payload error event separately.
                # Guarded against recursion — the marker payload is tiny.
                await PlatformEventService._emit_oversized_marker(
                    db, event_type, attempted, organization_id
                )

            # 2. Context propagation.
            request_id = request_id if request_id is not None else _current_request_id()
            session_id = session_id if session_id is not None else _current_session_id()
            job_run_id = job_run_id if job_run_id is not None else _current_job_run_id()

            # 3. Idempotency: app-level check-then-insert.
            #    Partitioned tables can't have unique indexes excluding the
            #    partition key (created_at). Acceptable race: same
            #    client_emit_id implies same emit call, not a real concurrent
            #    write, so we accept the very small window.
            if client_emit_id:
                existing = await db.execute(
                    text(
                        "SELECT 1 FROM platform_events "
                        "WHERE organization_id IS NOT DISTINCT FROM :org "
                        "AND client_emit_id = :cid LIMIT 1"
                    ),
                    {"org": organization_id, "cid": client_emit_id},
                )
                if existing.first() is not None:
                    return  # duplicate — silently skip

            # 4. Insert. `created_at` defaults to server-now; backfill
            #    callers may override with a historical timestamp.
            await db.execute(
                text(
                    """
                    INSERT INTO platform_events
                      (id, organization_id, actor_user_id, acting_as_user_id,
                       view_as_role, actor_type, actor_agent_type, event_type,
                       level, entity_refs, payload, request_id, session_id,
                       job_run_id, client_emit_id, created_at)
                    VALUES
                      (:id, :org, :actor_uid, :acting_uid, :view_role,
                       :atype, :aagent, :etype, :level, :refs, :payload,
                       :rid, :sid, :jid, :cid, COALESCE(:created_at, NOW()))
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": organization_id,
                    "actor_uid": actor.user_id,
                    "acting_uid": actor.acting_as_user_id,
                    "view_role": actor.view_as_role,
                    "atype": actor.actor_type,
                    "aagent": actor.actor_agent_type,
                    "etype": event_type,
                    "level": level,
                    "refs": json.dumps(entity_refs_obj),
                    "payload": json.dumps(payload_obj),
                    "rid": request_id,
                    "sid": session_id,
                    "jid": job_run_id,
                    "cid": client_emit_id,
                    "created_at": created_at,
                },
            )
        except Exception as e:  # noqa: BLE001 — by design, never raise
            logger.error(
                "platform_event.emit failed",
                extra={
                    "event_type": event_type,
                    "error": str(e)[:200],
                },
            )

    @staticmethod
    async def _emit_oversized_marker(
        db: AsyncSession,
        original_event_type: str,
        attempted_size_bytes: int,
        organization_id: Optional[str],
    ) -> None:
        """Record that an oversized payload was truncated. Fixed small shape
        so recursion can't chain (this event itself is well under 8KB)."""
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO platform_events
                      (id, organization_id, actor_type, event_type, level,
                       entity_refs, payload, created_at)
                    VALUES
                      (:id, :org, 'system', 'platform_event.oversized_payload',
                       'error', '{}'::jsonb, :payload, NOW())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": organization_id,
                    "payload": json.dumps(
                        {
                            "original_event_type": original_event_type,
                            "attempted_size_bytes": attempted_size_bytes,
                        }
                    ),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                "platform_event.oversized_marker emit failed",
                extra={"error": str(e)[:200]},
            )


# ---------------------------------------------------------------------------
# Context helpers — public so middleware/job_run_context can set them.
# ---------------------------------------------------------------------------


def set_request_id(value: Optional[str]):
    return _request_id_var.set(value)


def reset_request_id(token) -> None:
    _request_id_var.reset(token)


def set_session_id(value: Optional[str]):
    return _session_id_var.set(value)


def reset_session_id(token) -> None:
    _session_id_var.reset(token)


def set_job_run_id(value: Optional[str]):
    return _job_run_id_var.set(value)


def reset_job_run_id(token) -> None:
    _job_run_id_var.reset(token)
