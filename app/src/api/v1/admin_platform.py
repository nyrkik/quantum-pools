"""Platform-admin endpoints — QP staff only, cross-org.

These endpoints are distinct from the org-scoped `/admin/*` routes that
customer-admins use. Platform admins (`User.is_platform_admin = True`)
operate outside any single org: CCPA data-subject requests, cross-org
event queries (Step 12), Sonar read access (Phase 7).

The gating dependency is `get_platform_admin` in `src/api/deps.py` —
a non-platform-admin user gets 403, not an org-scoped fallback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
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
