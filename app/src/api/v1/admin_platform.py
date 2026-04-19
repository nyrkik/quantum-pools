"""Platform-admin endpoints — QP staff only, cross-org.

These endpoints are distinct from the org-scoped `/admin/*` routes that
customer-admins use. Platform admins (`User.is_platform_admin = True`)
operate outside any single org: CCPA data-subject requests, cross-org
event queries (Step 12), Sonar read access (Phase 7).

The gating dependency is `get_platform_admin` in `src/api/deps.py` —
a non-platform-admin user gets 403, not an org-scoped fallback.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_platform_admin, PlatformAdminContext

router = APIRouter(prefix="/admin/platform", tags=["platform-admin"])


class PurgeEventsResponse(BaseModel):
    request_id: str
    target_user_id: str
    rows_affected: int
    breakdown: dict[str, int]  # {actor_uid_nulled, acting_uid_nulled, entity_ref_cleared}
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

    Nulls every reference to `user_id` in the event stream:
      - actor_user_id
      - acting_as_user_id
      - entity_refs->>'user_id'

    The rows themselves stay — aggregate analytics (counts, rates,
    per-event_type distributions) continue to work; only the identifier
    is erased. One `data_deletion_requests` audit row per request.

    Intentionally does NOT emit a `platform_events` row for the purge
    itself — that would leak the very identifier we're erasing. The
    audit trail lives in `data_deletion_requests` and is
    platform-admin-only read access.
    """
    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # 1. Record the request (status: in-progress).
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
        {
            "id": request_id,
            "ts": now,
            "req_by": ctx.user.id,
            "tgt": user_id,
            "note": note,
        },
    )

    # 2. Execute all three identifier-clearing UPDATEs. One transaction
    #    (the caller's session); commit at the end.
    actor_uid_result = await db.execute(
        text("UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :u"),
        {"u": user_id},
    )
    acting_uid_result = await db.execute(
        text("UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :u"),
        {"u": user_id},
    )
    entity_ref_result = await db.execute(
        text(
            "UPDATE platform_events SET entity_refs = entity_refs - 'user_id' "
            "WHERE entity_refs @> jsonb_build_object('user_id', cast(:u as text))"
        ),
        {"u": user_id},
    )

    breakdown = {
        "actor_uid_nulled": actor_uid_result.rowcount or 0,
        "acting_uid_nulled": acting_uid_result.rowcount or 0,
        "entity_ref_cleared": entity_ref_result.rowcount or 0,
    }
    total = sum(breakdown.values())

    # 3. Mark the request completed with the rowcount.
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
