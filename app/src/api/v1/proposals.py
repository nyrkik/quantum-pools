"""Org-scoped proposal actions.

Different from `/admin/platform/proposals` (cross-org read-only for
Sonar + operator triage) — this is what the product UI calls when a
user clicks Accept / Edit & Accept / Reject on a `ProposalCard`.

All endpoints cross-org-guard: a proposal can only be resolved by a
user in the same org that staged it. Platform-admin bypass is NOT
offered here; staff use the admin endpoints.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import OrgUserContext, get_current_org_user
from src.core.database import get_db
from src.models.agent_proposal import AgentProposal
from src.services.events.actor_factory import actor_from_org_ctx
from src.services.proposals import ProposalService
from src.services.proposals.proposal_service import (
    ProposalStateError,
)
from src.services.workflow.config_service import WorkflowConfigService

router = APIRouter(prefix="/proposals", tags=["proposals"])


# -- Helpers ----------------------------------------------------------------


async def _load_org_scoped(
    db: AsyncSession, proposal_id: str, ctx: OrgUserContext,
) -> AgentProposal:
    """Load a proposal that belongs to the caller's org, or 404/403."""
    p = await db.get(AgentProposal, proposal_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if p.organization_id != ctx.organization_id:
        # Don't leak existence — return 404 as if it didn't exist.
        raise HTTPException(status_code=404, detail="Proposal not found")
    return p


def _serialize(p: AgentProposal) -> dict:
    """Wire shape for a proposal. Matches the admin endpoint's shape so
    the frontend has one mental model."""
    return {
        "id": p.id,
        "organization_id": p.organization_id,
        "agent_type": p.agent_type,
        "entity_type": p.entity_type,
        "source_type": p.source_type,
        "source_id": p.source_id,
        "proposed_payload": p.proposed_payload,
        "confidence": p.confidence,
        "input_context": p.input_context,
        "status": p.status,
        "rejected_permanently": p.rejected_permanently,
        "superseded_by_id": p.superseded_by_id,
        "outcome_entity_type": p.outcome_entity_type,
        "outcome_entity_id": p.outcome_entity_id,
        "user_delta": p.user_delta,
        "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
        "resolved_by_user_id": p.resolved_by_user_id,
        "resolution_note": p.resolution_note,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# -- Read -------------------------------------------------------------------


@router.get("")
async def list_proposals(
    entity_type: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List proposals scoped to the caller's org. Intended for UI surfaces
    like `/inbox/matches` (staged customer_match_suggestions) and the
    Phase 6 dashboard widget (staged workflow_observer proposals).
    Narrow filters only — no cursor/pagination yet; bump `limit` if needed.

    `status_` is the query-param `status` (keyword `status_` to avoid
    shadowing Python's builtin at the handler level).
    """
    from sqlalchemy import select
    q = select(AgentProposal).where(
        AgentProposal.organization_id == ctx.organization_id,
    )
    if entity_type:
        q = q.where(AgentProposal.entity_type == entity_type)
    if agent_type:
        q = q.where(AgentProposal.agent_type == agent_type)
    if status_:
        q = q.where(AgentProposal.status == status_)
    q = q.order_by(AgentProposal.created_at.desc()).limit(max(1, min(limit, 500)))
    rows = (await db.execute(q)).scalars().all()
    return {"items": [_serialize(p) for p in rows], "total": len(rows)}


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch a single proposal scoped to the caller's org. Used by
    ProposalCard and by the full editor when it pre-populates for
    edit-and-accept."""
    p = await _load_org_scoped(db, proposal_id, ctx)
    return _serialize(p)


# -- Actions ----------------------------------------------------------------


@router.post("/{proposal_id}/accept")
async def accept_proposal(
    proposal_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept as-is: creator runs with the staged payload; entity is
    created; proposal.accepted event fires; learning record written.
    Creator failure → rollback (proposal stays staged).

    Phase 4: the accept response also carries `next_step` — the
    inline UI step the org's workflow config dictates. Handler
    lookup failure NEVER rolls back the accept; worst case the user
    sees `next_step: null` and proceeds via the entity's detail page."""
    await _load_org_scoped(db, proposal_id, ctx)

    service = ProposalService(db)
    actor = actor_from_org_ctx(ctx)
    try:
        p, created = await service.accept(
            proposal_id=proposal_id,
            actor=actor,
        )
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))

    next_step = await WorkflowConfigService(db).resolve_next_step(
        proposal=p, created=created, org_id=ctx.organization_id, actor=actor,
    )
    await db.commit()

    return {
        "proposal": _serialize(p),
        "outcome_entity_id": getattr(created, "id", None),
        "outcome_entity_type": p.outcome_entity_type,
        "conflict": created is None,
        "next_step": next_step,
    }


class EditAndAcceptBody(BaseModel):
    edited_payload: dict[str, Any]
    note: Optional[str] = None


@router.post("/{proposal_id}/edit-and-accept")
async def edit_and_accept_proposal(
    proposal_id: str,
    body: EditAndAcceptBody,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Human edited the draft before accepting. Service computes the
    RFC 6902 patch as `user_delta`, records learning with the delta,
    runs the creator with the edited payload. Phase 4 next_step
    resolution mirrors the plain accept path."""
    await _load_org_scoped(db, proposal_id, ctx)

    service = ProposalService(db)
    actor = actor_from_org_ctx(ctx)
    try:
        p, created = await service.edit_and_accept(
            proposal_id=proposal_id,
            actor=actor,
            edited_payload=body.edited_payload,
            note=body.note,
        )
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))

    next_step = await WorkflowConfigService(db).resolve_next_step(
        proposal=p, created=created, org_id=ctx.organization_id, actor=actor,
    )
    await db.commit()

    return {
        "proposal": _serialize(p),
        "outcome_entity_id": getattr(created, "id", None),
        "outcome_entity_type": p.outcome_entity_type,
        "conflict": created is None,
        "next_step": next_step,
    }


class RejectBody(BaseModel):
    permanently: bool = False
    note: Optional[str] = None


@router.post("/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    body: RejectBody = Body(default_factory=RejectBody),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reject. `permanently=true` adds a strong learning signal so the
    agent stops producing similar proposals (non-blocking — lessons,
    not brittle rules)."""
    await _load_org_scoped(db, proposal_id, ctx)

    service = ProposalService(db)
    try:
        p = await service.reject(
            proposal_id=proposal_id,
            actor=actor_from_org_ctx(ctx),
            permanently=body.permanently,
            note=body.note,
        )
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()

    return {"proposal": _serialize(p)}
