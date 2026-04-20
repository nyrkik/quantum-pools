"""Workflow config API — per-org post-creation handler configuration.

GET is open to any org user — the frontend uses it to know which
next_step components to prepare to render. PUT is gated by
`workflow.manage_config` (new Phase 4 permission slug).

Surface:
    GET  /v1/workflow/config           → current effective config
    PUT  /v1/workflow/config           → upsert (workflow.manage_config)
    GET  /v1/workflow/handlers         → registry listing for the UI
"""

from __future__ import annotations

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
