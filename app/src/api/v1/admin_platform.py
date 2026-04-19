"""Platform-admin endpoints — QP staff only, cross-org.

These endpoints are distinct from the org-scoped `/admin/*` routes that
customer-admins use. Platform admins (`User.is_platform_admin = True`)
operate outside any single org: CCPA data-subject requests, cross-org
event queries (Step 12), Sonar read access (Phase 7).

The gating dependency is `get_platform_admin` in `src/api/deps.py` —
a non-platform-admin user gets 403, not an org-scoped fallback.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_platform_admin, PlatformAdminContext
from src.utils.notify import send_ntfy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/platform", tags=["platform-admin"])


class PurgeEventsResponse(BaseModel):
    request_id: str
    target_user_id: str
    rows_affected: int
    breakdown: dict[str, int]  # {actor_uid_nulled, acting_uid_nulled, entity_refs_scrubbed}
    completed_at: str


@router.post(
    "/users/{user_id}/purge-events",
    response_model=PurgeEventsResponse,
    status_code=200,
)
async def purge_user_events(
    user_id: str,
    note: Optional[str] = Body(None, embed=True),
    ctx: PlatformAdminContext = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> PurgeEventsResponse:
    """CCPA data-subject purge for `platform_events`.

    Under the phase-1 privacy contract (docs/event-taxonomy.md §6):
    user IDs live ONLY in `actor_user_id`, `acting_as_user_id`, and
    `entity_refs` (any key whose VALUE equals the user_id — not just
    the literal 'user_id' key). Payload fields NEVER carry user
    identifiers. That constraint makes purge both auditable and
    correct: three axes to clear, no recursive payload scan needed.

    The event rows themselves stay. Aggregate analytics (counts, rates,
    per-event_type distributions) keep working; only the identifier is
    erased. One `data_deletion_requests` audit row per request, and
    critically — the audit row is committed in its own transaction
    BEFORE the purge UPDATEs. A failed purge still leaves a trail.

    Does NOT emit a `platform_events` row for the purge itself — that
    would leak the very identifier we're erasing. Audit lives only in
    `data_deletion_requests` (platform-admin-only read).
    """
    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # --- TX 1: persist the audit row so a mid-purge failure still has a
    # trail. Compliance-grade endpoints don't lose request records on a
    # downstream error.
    await db.execute(
        text(
            """
            INSERT INTO data_deletion_requests
              (id, requested_at, requested_by_user_id, target_user_id,
               target_type, scope, note)
            VALUES
              (:id, :ts, :req_by, :tgt, 'user',
               '{"table": "platform_events", "operation": "null_identifiers"}'::jsonb,
               :note)
            """
        ),
        {"id": request_id, "ts": now, "req_by": ctx.user.id, "tgt": user_id, "note": note},
    )
    await db.commit()

    logger.info(
        "ccpa_purge.start request_id=%s target=%s by=%s note=%r",
        request_id, user_id, ctx.user.id, note,
    )

    try:
        # --- TX 2: the actual purge. Three axes.
        #
        # 1. Direct actor.
        actor_result = await db.execute(
            text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
            {"u": user_id},
        )
        # 2. Acting-as (impersonation trail).
        acting_result = await db.execute(
            text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
            {"u": user_id},
        )
        # 3. entity_refs — deep scan by VALUE. Removes any key whose
        #    value equals :u, regardless of key name
        #    (user_id / prior_manager_user_id / prior_assignee_user_id / etc).
        #    The WHERE EXISTS is the index-friendly filter; the SET
        #    rebuilds without any matching entry.
        entity_result = await db.execute(
            text(
                """
                UPDATE platform_events
                SET entity_refs = (
                    SELECT COALESCE(jsonb_object_agg(key, value), '{}'::jsonb)
                    FROM jsonb_each(entity_refs)
                    WHERE value #>> '{}' IS DISTINCT FROM :u
                )
                WHERE EXISTS (
                    SELECT 1 FROM jsonb_each(entity_refs)
                    WHERE value #>> '{}' = :u
                )
                """
            ),
            {"u": user_id},
        )

        breakdown = {
            "actor_uid_nulled": actor_result.rowcount or 0,
            "acting_uid_nulled": acting_result.rowcount or 0,
            "entity_refs_scrubbed": entity_result.rowcount or 0,
        }
        total = sum(breakdown.values())

        # Mark the audit row completed.
        completed_at = datetime.now(timezone.utc)
        await db.execute(
            text(
                "UPDATE data_deletion_requests "
                "SET completed_at = :ts, completed_rows_affected = :n "
                "WHERE id = :rid"
            ),
            {"ts": completed_at, "n": total, "rid": request_id},
        )
        await db.commit()

    except Exception as e:  # noqa: BLE001
        # Audit row is already committed; log + alert so the failure is
        # visible even though the endpoint raises.
        logger.error(
            "ccpa_purge.failed request_id=%s target=%s error=%s",
            request_id, user_id, e,
        )
        send_ntfy(
            title="CCPA purge FAILED",
            body=f"request={request_id} target={user_id} err={type(e).__name__}: {e}",
            priority="high",
            tags="warning",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "purge_failed",
                "message": "Purge UPDATE raised — audit row kept, no data cleared. See logs.",
                "request_id": request_id,
            },
        )

    # Success path — emit the audit alert regardless of rowcount
    # (low-traffic, high-ceremony event; no cooldown).
    logger.info(
        "ccpa_purge.complete request_id=%s target=%s rows=%d breakdown=%s",
        request_id, user_id, total, breakdown,
    )
    send_ntfy(
        title=f"CCPA purge completed ({total} rows)",
        body=(
            f"request={request_id}\n"
            f"target={user_id}\n"
            f"by={ctx.user.id}\n"
            f"breakdown={breakdown}\n"
            f"note={note!r}"
        ),
        priority="default",
        tags="shield",
    )

    return PurgeEventsResponse(
        request_id=request_id,
        target_user_id=user_id,
        rows_affected=total,
        breakdown=breakdown,
        completed_at=completed_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Event query endpoint (Phase 1 Step 12)
# ---------------------------------------------------------------------------

# Opaque pagination cursors encode (created_at_iso, id) so the next page
# condition — `(created_at, id) < (cursor.created_at, cursor.id)` — uses
# the composite partition+PK index cleanly. Base64 encoding is just so
# callers treat it as opaque; the value is not secret.


def _encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = json.dumps({"ts": created_at.isoformat(), "id": row_id}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        obj = json.loads(raw)
        return datetime.fromisoformat(obj["ts"]), obj["id"]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "message": f"Could not decode cursor: {e}"},
        )


def _parse_entity_ref(raw: str) -> tuple[str, str]:
    """`customer_id:abc-123` → ('customer_id', 'abc-123')."""
    if ":" not in raw:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_entity_ref",
                "message": f"entity_ref must be 'key:value', got: {raw!r}",
            },
        )
    key, _, value = raw.partition(":")
    if not key or not value:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_entity_ref", "message": "key and value both required"},
        )
    return key, value


@router.get("/events", status_code=200)
async def query_events(
    org_id: Optional[str] = Query(None, description="Filter by organization_id (UUID). Omit for cross-org (platform-level events included)."),
    event_type: Optional[str] = Query(None, description="Exact event_type match (e.g. 'thread.archived')."),
    event_type_prefix: Optional[str] = Query(None, description="Prefix match (e.g. 'thread.' matches thread.archived, thread.opened, etc.). Exclusive with event_type."),
    entity_ref: Optional[list[str]] = Query(None, description="Entity-ref filter as 'key:value' (e.g. 'customer_id:abc'). Repeat the param to AND multiple filters."),
    actor_user_id: Optional[str] = Query(None, description="Filter by actor_user_id exact match."),
    actor_type: Optional[str] = Query(None, description="Filter by actor_type enum (user|system|agent)."),
    level: Optional[str] = Query(None, description="Filter by level (user_action|system_action|agent_action|error)."),
    from_: Optional[datetime] = Query(None, alias="from", description="Lower bound on created_at (inclusive). ISO 8601. Defaults to 30 days ago when omitted."),
    to: Optional[datetime] = Query(None, description="Upper bound on created_at (exclusive). ISO 8601. Defaults to now."),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from a prior response. Advances past that row."),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return. 1..500."),
    ctx: PlatformAdminContext = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cross-org read-only event query.

    For Sonar's ad-hoc analysis and Brian's debugging. Rows are returned
    newest-first. Pagination is cursor-based over `(created_at DESC, id DESC)`
    so the response can be resumed efficiently across partition boundaries.

    A `from` default of 30 days is applied when omitted so a forgotten
    filter doesn't accidentally scan 2+ years of partitions. Pass
    `from=1970-01-01T00:00:00Z` to query across the full history.
    """
    if event_type and event_type_prefix:
        raise HTTPException(
            status_code=400,
            detail={"error": "conflicting_filters", "message": "event_type and event_type_prefix are exclusive"},
        )

    now = datetime.now(timezone.utc)
    if from_ is None:
        from_ = now - timedelta(days=30)
    if to is None:
        to = now

    # Normalize to UTC so asyncpg/Postgres timestamptz binding is consistent.
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    where_clauses = ["created_at >= :from_", "created_at < :to"]
    params: dict[str, Any] = {"from_": from_, "to": to}

    if org_id is not None:
        # Explicit "" (empty) means "platform events only"; None means no filter.
        if org_id == "":
            where_clauses.append("organization_id IS NULL")
        else:
            where_clauses.append("organization_id = :org_id")
            params["org_id"] = org_id

    if event_type:
        where_clauses.append("event_type = :etype")
        params["etype"] = event_type

    if event_type_prefix:
        where_clauses.append("event_type LIKE :etype_prefix")
        params["etype_prefix"] = event_type_prefix + "%"

    if actor_user_id:
        where_clauses.append("actor_user_id = :actor_uid")
        params["actor_uid"] = actor_user_id

    if actor_type:
        where_clauses.append("actor_type = :atype")
        params["atype"] = actor_type

    if level:
        where_clauses.append("level = :lvl")
        params["lvl"] = level

    if entity_ref:
        for i, raw in enumerate(entity_ref):
            k, v = _parse_entity_ref(raw)
            # JSONB containment against {k: v} — uses the GIN index on entity_refs.
            where_clauses.append(f"entity_refs @> cast(:er_{i} AS jsonb)")
            params[f"er_{i}"] = json.dumps({k: v})

    if cursor:
        cur_ts, cur_id = _decode_cursor(cursor)
        # Row-value comparison uses (created_at DESC, id DESC) ordering.
        where_clauses.append("(created_at, id) < (:cur_ts, :cur_id)")
        params["cur_ts"] = cur_ts
        params["cur_id"] = cur_id

    sql = (
        "SELECT id, organization_id, actor_user_id, acting_as_user_id, "
        "view_as_role, actor_type, actor_agent_type, event_type, level, "
        "entity_refs, payload, request_id, session_id, job_run_id, "
        "client_emit_id, created_at "
        "FROM platform_events "
        f"WHERE {' AND '.join(where_clauses)} "
        "ORDER BY created_at DESC, id DESC "
        "LIMIT :limit"
    )
    params["limit"] = limit

    logger.info(
        "admin_events.query by=%s filters=%s limit=%d",
        ctx.user.id,
        {k: v for k, v in params.items() if k not in {"limit", "cur_ts", "cur_id"}},
        limit,
    )

    rows = (await db.execute(text(sql), params)).all()

    events = [
        {
            "id": r[0],
            "organization_id": r[1],
            "actor_user_id": r[2],
            "acting_as_user_id": r[3],
            "view_as_role": r[4],
            "actor_type": r[5],
            "actor_agent_type": r[6],
            "event_type": r[7],
            "level": r[8],
            "entity_refs": r[9],
            "payload": r[10],
            "request_id": r[11],
            "session_id": r[12],
            "job_run_id": r[13],
            "client_emit_id": r[14],
            "created_at": r[15].isoformat() if r[15] else None,
        }
        for r in rows
    ]

    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = _encode_cursor(last[15], last[0])

    return {
        "events": events,
        "next_cursor": next_cursor,
        "window": {"from": from_.isoformat(), "to": to.isoformat()},
        "count": len(events),
    }


# ---------------------------------------------------------------------------
# Proposals query endpoint (Phase 2 Step 7)
# ---------------------------------------------------------------------------
#
# Mirrors /events — same cursor pagination, same platform-admin gate.
# Sonar + operator triage read here to see the proposal stream across
# orgs: "what's the inbox summarizer proposing today and how often is
# the user accepting?"


@router.get("/proposals", status_code=200)
async def query_proposals(
    org_id: Optional[str] = Query(None, description="Filter by organization_id (UUID)."),
    agent_type: Optional[str] = Query(None, description="Filter by agent_type (e.g. 'inbox_summarizer')."),
    entity_type: Optional[str] = Query(None, description="Filter by entity_type (e.g. 'job', 'estimate', 'equipment_item')."),
    status_: Optional[str] = Query(
        None, alias="status",
        description="Filter by status (staged|accepted|edited|rejected|expired|superseded).",
    ),
    source_type: Optional[str] = Query(None, description="Filter by source_type (e.g. 'deepblue_conversation')."),
    source_id: Optional[str] = Query(None, description="Filter by source_id exact match."),
    from_: Optional[datetime] = Query(None, alias="from", description="Lower bound on created_at. Defaults to 30 days ago."),
    to: Optional[datetime] = Query(None, description="Upper bound on created_at."),
    cursor: Optional[str] = Query(None, description="Opaque cursor from a prior response."),
    limit: int = Query(50, ge=1, le=500, description="Max rows. 1..500."),
    ctx: PlatformAdminContext = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cross-org read-only proposals query.

    Pagination same as /events (cursor over `(created_at DESC, id DESC)`).
    `from` defaults to 30 days back to avoid accidental full-table scans.
    """
    now = datetime.now(timezone.utc)
    if from_ is None:
        from_ = now - timedelta(days=30)
    if to is None:
        to = now
    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    where_clauses = ["created_at >= :from_", "created_at < :to"]
    params: dict[str, Any] = {"from_": from_, "to": to}

    if org_id:
        where_clauses.append("organization_id = :org_id")
        params["org_id"] = org_id
    if agent_type:
        where_clauses.append("agent_type = :atype")
        params["atype"] = agent_type
    if entity_type:
        where_clauses.append("entity_type = :etype")
        params["etype"] = entity_type
    if status_:
        where_clauses.append("status = :st")
        params["st"] = status_
    if source_type:
        where_clauses.append("source_type = :src_t")
        params["src_t"] = source_type
    if source_id:
        where_clauses.append("source_id = :src_id")
        params["src_id"] = source_id

    if cursor:
        cur_ts, cur_id = _decode_cursor(cursor)
        where_clauses.append("(created_at, id) < (:cur_ts, :cur_id)")
        params["cur_ts"] = cur_ts
        params["cur_id"] = cur_id

    sql = (
        "SELECT id, organization_id, agent_type, entity_type, "
        "source_type, source_id, proposed_payload, confidence, "
        "status, rejected_permanently, superseded_by_id, "
        "outcome_entity_type, outcome_entity_id, user_delta, "
        "resolved_at, resolved_by_user_id, resolution_note, "
        "created_at, updated_at "
        "FROM agent_proposals "
        f"WHERE {' AND '.join(where_clauses)} "
        "ORDER BY created_at DESC, id DESC "
        "LIMIT :limit"
    )
    params["limit"] = limit

    logger.info(
        "admin_proposals.query by=%s filters=%s limit=%d",
        ctx.user.id,
        {k: v for k, v in params.items() if k not in {"limit", "cur_ts", "cur_id"}},
        limit,
    )

    rows = (await db.execute(text(sql), params)).all()
    items = [
        {
            "id": r[0],
            "organization_id": r[1],
            "agent_type": r[2],
            "entity_type": r[3],
            "source_type": r[4],
            "source_id": r[5],
            "proposed_payload": r[6],
            "confidence": r[7],
            "status": r[8],
            "rejected_permanently": r[9],
            "superseded_by_id": r[10],
            "outcome_entity_type": r[11],
            "outcome_entity_id": r[12],
            "user_delta": r[13],
            "resolved_at": r[14].isoformat() if r[14] else None,
            "resolved_by_user_id": r[15],
            "resolution_note": r[16],
            "created_at": r[17].isoformat() if r[17] else None,
            "updated_at": r[18].isoformat() if r[18] else None,
        }
        for r in rows
    ]

    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        # Use created_at + id for cursor. Column positions: 17 = created_at, 0 = id.
        next_cursor = _encode_cursor(last[17], last[0])

    return {
        "proposals": items,
        "next_cursor": next_cursor,
        "window": {"from": from_.isoformat(), "to": to.isoformat()},
        "count": len(items),
    }


# ---------------------------------------------------------------------------
# Org feature-flag toggles (Phase 3+)
# ---------------------------------------------------------------------------
#
# Per-org UX rollout flags live on the `organizations` table as
# booleans (not FeatureService slugs — these are rollout gates, not
# paywalls). Platform admins toggle them here.


class InboxV2FlagRequest(BaseModel):
    enabled: bool


@router.post("/orgs/{org_id}/inbox-v2", status_code=200)
async def toggle_inbox_v2(
    org_id: str,
    body: InboxV2FlagRequest,
    ctx: PlatformAdminContext = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Turn the inbox-v2 redesign on or off for a single org.

    On flip-on, queue every existing thread that doesn't yet have a
    cached summary by setting ai_summary_debounce_until = NOW(). The
    sweep (bounded ~80/min) drains the backlog gradually without
    spiking Anthropic rate limits. Without this backfill the inbox
    would show "awaiting summary" indefinitely until each thread
    received a new inbound message.

    Flip-off: new inbounds stop queueing summaries, cached payloads
    stay put — the frontend honors the flag so the redesigned layout
    simply hides.
    """
    from sqlalchemy import text as _text
    from src.models.organization import Organization

    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    prior = org.inbox_v2_enabled
    org.inbox_v2_enabled = bool(body.enabled)

    queued = 0
    if (not prior) and org.inbox_v2_enabled:
        # Only queue threads that (a) haven't been summarized yet and
        # (b) aren't already queued. Threads with cached summaries stay
        # put; the nightly stale sweep will refresh them on schedule.
        result = await db.execute(
            _text(
                """
                UPDATE agent_threads
                   SET ai_summary_debounce_until = NOW()
                 WHERE organization_id = :org_id
                   AND ai_summary_payload IS NULL
                   AND ai_summary_debounce_until IS NULL
                   AND message_count > 0
                """
            ),
            {"org_id": org_id},
        )
        queued = result.rowcount or 0

    await db.commit()

    logger.info(
        "inbox_v2 toggled for org %s by platform-admin %s: %s → %s (backfill queued=%d)",
        org_id, ctx.user.id, prior, org.inbox_v2_enabled, queued,
    )

    return {
        "org_id": org_id,
        "org_name": org.name,
        "inbox_v2_enabled": org.inbox_v2_enabled,
        "changed": prior != org.inbox_v2_enabled,
        "backfill_queued": queued,
    }


@router.get("/data-deletion-requests", status_code=200)
async def list_data_deletion_requests(
    limit: int = 50,
    ctx: PlatformAdminContext = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read-only audit of prior purge-on-request runs."""
    limit = max(1, min(limit, 500))
    rows = (await db.execute(
        text(
            "SELECT id, requested_at, requested_by_user_id, target_user_id, "
            "target_type, scope, completed_at, completed_rows_affected, note "
            "FROM data_deletion_requests "
            "ORDER BY requested_at DESC LIMIT :n"
        ),
        {"n": limit},
    )).all()
    return {
        "requests": [
            {
                "id": r[0],
                "requested_at": r[1].isoformat() if r[1] else None,
                "requested_by_user_id": r[2],
                "target_user_id": r[3],
                "target_type": r[4],
                "scope": r[5],
                "completed_at": r[6].isoformat() if r[6] else None,
                "rows_affected": r[7],
                "note": r[8],
            }
            for r in rows
        ],
    }
