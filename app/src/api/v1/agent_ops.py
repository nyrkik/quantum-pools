"""Agent operations API — observability, evals, drift detection."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import require_roles, OrgUserContext
from src.models.organization_user import OrgRole

router = APIRouter(prefix="/agent-ops", tags=["agent-ops"])


@router.get("/metrics")
async def get_metrics(
    agent: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
):
    """Get agent performance metrics."""
    from src.services.agents.observability import get_agent_metrics
    return await get_agent_metrics(ctx.organization_id, agent, hours)


@router.get("/drift/{agent_name}")
async def get_drift(
    agent_name: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
):
    """Get drift report for an agent — current vs baseline."""
    from src.services.agents.evals import get_drift_report
    return await get_drift_report(agent_name, ctx.organization_id)


@router.post("/eval/{agent_name}")
async def run_evals(
    agent_name: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
):
    """Run eval suite for an agent."""
    from src.services.agents.evals import run_eval_suite
    return await run_eval_suite(agent_name, ctx.organization_id)


@router.get("/logs")
async def get_logs(
    agent: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    success_only: Optional[bool] = Query(None),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Get recent agent logs."""
    from sqlalchemy import select, desc
    from src.services.agents.observability import AgentLog

    query = select(AgentLog).where(
        AgentLog.organization_id == ctx.organization_id
    ).order_by(desc(AgentLog.created_at)).limit(limit)

    if agent:
        query = query.where(AgentLog.agent_name == agent)
    if success_only is not None:
        query = query.where(AgentLog.success == success_only)

    result = await db.execute(query)
    return [
        {
            "id": l.id,
            "agent_name": l.agent_name,
            "action": l.action,
            "input_summary": l.input_summary[:200] if l.input_summary else None,
            "output_summary": l.output_summary[:200] if l.output_summary else None,
            "success": l.success,
            "error": l.error,
            "model": l.model,
            "input_tokens": l.input_tokens,
            "output_tokens": l.output_tokens,
            "cost_usd": l.cost_usd,
            "duration_ms": l.duration_ms,
            "created_at": l.created_at.isoformat(),
        }
        for l in result.scalars().all()
    ]
