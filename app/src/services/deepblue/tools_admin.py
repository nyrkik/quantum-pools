"""DeepBlue tools — Admin / System domain."""

import json
import logging

from sqlalchemy import select, desc

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_org_info(inp: dict, ctx: ToolContext) -> dict:
    """Get the organization's own profile (name, phone, addresses, branding)."""
    from src.models.organization import Organization

    org = (await ctx.db.execute(
        select(Organization).where(Organization.id == ctx.org_id)
    )).scalar_one_or_none()
    if not org:
        return {"error": "Organization not found"}

    # Parse structured addresses and resolve same_as references
    addresses = {}
    if org.addresses:
        try:
            raw = json.loads(org.addresses)
            # Resolve same_as references
            resolved = {}
            for key, val in raw.items():
                if isinstance(val, dict) and "same_as" in val:
                    source = raw.get(val["same_as"], {})
                    if isinstance(source, dict) and "same_as" not in source:
                        resolved[key] = {**source, "_same_as": val["same_as"]}
                    else:
                        resolved[key] = val
                else:
                    resolved[key] = val
            addresses = resolved
        except json.JSONDecodeError:
            pass

    # Fallback to flat fields if no structured addresses
    if not addresses and (org.address or org.city):
        addresses = {
            "mailing": {
                "street": org.address or "",
                "city": org.city or "",
                "state": org.state or "",
                "zip": org.zip_code or "",
            }
        }

    return {
        "name": org.name,
        "phone": org.phone,
        "email": org.email,
        "tagline": org.tagline,
        "addresses": addresses,
        "service_area": org.agent_service_area,
        "billing_email": org.billing_email,
    }


async def _exec_agent_health(inp: dict, ctx: ToolContext) -> dict:
    """Get AI agent health metrics + recent failures."""
    from src.services.agents.observability import get_agent_metrics, AgentLog
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    hours = inp.get("hours", 24)
    agent_filter = inp.get("agent_name")

    metrics = await get_agent_metrics(ctx.org_id, agent_filter, hours)

    # Recent failures (last 10)
    cutoff = _dt.now(_tz.utc) - _td(hours=hours)
    fail_query = select(AgentLog).where(
        AgentLog.organization_id == ctx.org_id,
        AgentLog.created_at >= cutoff,
        AgentLog.success == False,
    )
    if agent_filter:
        fail_query = fail_query.where(AgentLog.agent_name == agent_filter)
    fail_query = fail_query.order_by(desc(AgentLog.created_at)).limit(10)

    failures = (await ctx.db.execute(fail_query)).scalars().all()
    recent_failures = [
        {
            "agent": f.agent_name,
            "action": f.action,
            "error": (f.error or "")[:200],
            "when": f.created_at.isoformat() if f.created_at else None,
        }
        for f in failures
    ]

    return {
        "window_hours": hours,
        "agent_filter": agent_filter,
        "metrics": metrics,
        "recent_failures": recent_failures,
    }


async def _exec_query_database(inp: dict, ctx: ToolContext) -> dict:
    """Meta-tool: run a validated, read-only, org-scoped SELECT query."""
    from src.services.deepblue.sql_executor import execute_safe_query
    try:
        return await execute_safe_query(
            db=ctx.db,
            org_id=ctx.org_id,
            query=inp.get("query", ""),
            reason=inp.get("reason", ""),
        )
    except Exception as e:
        logger.error(f"query_database failed: {e}")
        return {"error": str(e)}


EXECUTORS = {
    "get_organization_info": _exec_org_info,
    "get_agent_health": _exec_agent_health,
    "query_database": _exec_query_database,
}
