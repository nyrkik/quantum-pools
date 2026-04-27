"""Workflow config API — per-org post-creation handler configuration
plus Phase 6 workflow_observer mute-list management.

GETs on /config and /handlers are open to any org user — the frontend
uses them to render the right next_step UI even for roles that can't
change config. PUT /config is gated by `workflow.manage_config` (Phase
4). The observer mute endpoints are gated by `workflow.review`
(Phase 6).

Surface:
    GET    /v1/workflow/config                   → current effective config
    PUT    /v1/workflow/config                   → upsert (workflow.manage_config)
    GET    /v1/workflow/handlers                 → registry listing
    GET    /v1/workflow/observer-mutes           → muted detector ids (workflow.review)
    PUT    /v1/workflow/observer-mutes/{id}      → mute detector (workflow.review)
    DELETE /v1/workflow/observer-mutes/{id}      → unmute detector (workflow.review)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    OrgUserContext,
    get_current_org_user,
    require_permissions,
)
from src.core.database import get_db
from src.models.org_workflow_config import OrgWorkflowConfig
from src.services.events.actor_factory import actor_from_org_ctx
from src.services.workflow.config_service import (
    UnknownHandlerError,
    WorkflowConfigService,
)
from src.services.workflow.registry import HANDLERS

router = APIRouter(prefix="/workflow", tags=["workflow"])


class WorkflowConfigBody(BaseModel):
    post_creation_handlers: dict[str, str]
    default_assignee_strategy: dict[str, Any]


@router.get("/config")
async def get_workflow_config(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the effective config (row or system defaults).

    Read is intentionally ungated: the frontend needs this even for
    roles that can't change it so it knows which step component to
    render on accept."""
    return await WorkflowConfigService(db).get_or_default(ctx.organization_id)


@router.put("/config")
async def put_workflow_config(
    body: WorkflowConfigBody,
    ctx: OrgUserContext = Depends(
        require_permissions("workflow.manage_config")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        after = await WorkflowConfigService(db).put(
            org_id=ctx.organization_id,
            post_creation_handlers=body.post_creation_handlers,
            default_assignee_strategy=body.default_assignee_strategy,
            actor=actor_from_org_ctx(ctx),
        )
    except UnknownHandlerError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return after


@router.get("/handlers")
async def list_handlers(
    ctx: OrgUserContext = Depends(get_current_org_user),
) -> dict:
    """Listing the registry so the Settings UI can render the real
    plain-language options without hard-coding names. The UI owns
    the descriptions (NOT backend) per the spec's no-enum-vocabulary
    rule; this endpoint just tells the UI which keys are valid."""
    _ = ctx  # read-only, no filtering required
    return {
        "handlers": [
            {"name": name, "entity_types": list(h.entity_types)}
            for name, h in sorted(HANDLERS.items())
        ],
    }


# ---------------------------------------------------------------------------
# Phase 6: workflow_observer mute list
# ---------------------------------------------------------------------------


async def _ensure_config_row(db: AsyncSession, org_id: str) -> OrgWorkflowConfig:
    """Lazy-create the config row so mute writes don't have to think
    about whether one exists yet."""
    row = await db.get(OrgWorkflowConfig, org_id)
    if row is None:
        row = OrgWorkflowConfig(
            organization_id=org_id,
            post_creation_handlers={},
            default_assignee_strategy={"strategy": "last_used_in_org"},
            observer_mutes={},
            observer_thresholds={},
        )
        db.add(row)
        await db.flush()
    return row


@router.get("/observer-mutes")
async def list_observer_mutes(
    ctx: OrgUserContext = Depends(require_permissions("workflow.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the org's muted-detector map — `{detector_id: {muted_at,
    muted_by_user_id}}`. The dashboard surface uses this to mark which
    suggestion classes the org has opted out of."""
    row = await db.get(OrgWorkflowConfig, ctx.organization_id)
    return {"mutes": (row.observer_mutes if row else None) or {}}


@router.put("/observer-mutes/{detector_id}")
async def mute_observer_detector(
    detector_id: str,
    ctx: OrgUserContext = Depends(require_permissions("workflow.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add the detector to the mute list. Idempotent — re-muting an
    already-muted detector updates the timestamp/user without error."""
    if not detector_id or len(detector_id) > 64:
        raise HTTPException(400, "detector_id must be 1-64 chars")
    row = await _ensure_config_row(db, ctx.organization_id)
    mutes = dict(row.observer_mutes or {})
    mutes[detector_id] = {
        "muted_at": datetime.now(timezone.utc).isoformat(),
        "muted_by_user_id": ctx.user.id,
    }
    row.observer_mutes = mutes
    await db.commit()
    return {"detector_id": detector_id, "muted": True, "mutes": mutes}


@router.delete("/observer-mutes/{detector_id}")
async def unmute_observer_detector(
    detector_id: str,
    ctx: OrgUserContext = Depends(require_permissions("workflow.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove the detector from the mute list. Idempotent — unmuting
    a non-muted detector is a no-op success."""
    row = await db.get(OrgWorkflowConfig, ctx.organization_id)
    if row is None or detector_id not in (row.observer_mutes or {}):
        return {"detector_id": detector_id, "muted": False, "mutes": {}}
    mutes = dict(row.observer_mutes)
    mutes.pop(detector_id, None)
    row.observer_mutes = mutes
    await db.commit()
    return {"detector_id": detector_id, "muted": False, "mutes": mutes}
