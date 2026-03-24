"""Agent observability — logs every agent call with input, output, cost, timing.

This is the foundation for evals, drift detection, and debugging.
Every agent should call `log_agent_call()` when it completes work.
"""

import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, get_db_context

logger = logging.getLogger(__name__)


class AgentLog(Base):
    """Immutable log of every agent invocation."""
    __tablename__ = "agent_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_name: Mapped[str] = mapped_column(String(50), index=True)  # classifier, customer_matcher, etc.
    action: Mapped[str] = mapped_column(String(100))  # classify_email, match_customer, etc.
    input_summary: Mapped[str | None] = mapped_column(Text)  # truncated input for debugging
    output_summary: Mapped[str | None] = mapped_column(Text)  # truncated output
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(50))  # claude-haiku-4-5, etc.
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    extra_data: Mapped[str | None] = mapped_column(Text)  # JSON for agent-specific data
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Cost per 1M tokens (approximate)
MODEL_COSTS = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    costs = MODEL_COSTS.get(model, {"input": 1.0, "output": 5.0})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


class AgentTimer:
    """Context manager to time agent operations."""
    def __init__(self):
        self.start_time = None
        self.duration_ms = 0

    def __enter__(self):
        self.start_time = time.monotonic()
        return self

    def __exit__(self, *args):
        self.duration_ms = int((time.monotonic() - self.start_time) * 1000)


async def log_agent_call(
    organization_id: str,
    agent_name: str,
    action: str,
    input_summary: str = "",
    output_summary: str = "",
    success: bool = True,
    error: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_ms: int | None = None,
    extra_data: str | None = None,
):
    """Log an agent invocation. Fire-and-forget — never blocks the caller."""
    try:
        cost = None
        if model and input_tokens and output_tokens:
            cost = estimate_cost(model, input_tokens, output_tokens)

        async with get_db_context() as db:
            log = AgentLog(
                organization_id=organization_id,
                agent_name=agent_name,
                action=action,
                input_summary=input_summary[:2000] if input_summary else None,
                output_summary=output_summary[:2000] if output_summary else None,
                success=success,
                error=error[:1000] if error else None,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                duration_ms=duration_ms,
                extra_data=extra_data,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        # Never let logging break the agent
        logger.error(f"Failed to log agent call: {e}")


async def get_agent_metrics(organization_id: str, agent_name: str | None = None, hours: int = 24) -> dict:
    """Get aggregate metrics for agents over a time window."""
    from sqlalchemy import select, func
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with get_db_context() as db:
        base = select(AgentLog).where(
            AgentLog.organization_id == organization_id,
            AgentLog.created_at >= cutoff,
        )
        if agent_name:
            base = base.where(AgentLog.agent_name == agent_name)

        # Total calls
        total = (await db.execute(
            select(func.count(AgentLog.id)).where(
                AgentLog.organization_id == organization_id,
                AgentLog.created_at >= cutoff,
                *([AgentLog.agent_name == agent_name] if agent_name else []),
            )
        )).scalar() or 0

        # Failures
        failures = (await db.execute(
            select(func.count(AgentLog.id)).where(
                AgentLog.organization_id == organization_id,
                AgentLog.created_at >= cutoff,
                AgentLog.success == False,
                *([AgentLog.agent_name == agent_name] if agent_name else []),
            )
        )).scalar() or 0

        # Cost
        total_cost = (await db.execute(
            select(func.sum(AgentLog.cost_usd)).where(
                AgentLog.organization_id == organization_id,
                AgentLog.created_at >= cutoff,
                *([AgentLog.agent_name == agent_name] if agent_name else []),
            )
        )).scalar() or 0.0

        # Avg duration
        avg_duration = (await db.execute(
            select(func.avg(AgentLog.duration_ms)).where(
                AgentLog.organization_id == organization_id,
                AgentLog.created_at >= cutoff,
                *([AgentLog.agent_name == agent_name] if agent_name else []),
            )
        )).scalar()

        # Per-agent breakdown
        breakdown = {}
        if not agent_name:
            result = await db.execute(
                select(AgentLog.agent_name, func.count(AgentLog.id), func.sum(AgentLog.cost_usd))
                .where(AgentLog.organization_id == organization_id, AgentLog.created_at >= cutoff)
                .group_by(AgentLog.agent_name)
            )
            for name, count, cost in result.all():
                breakdown[name] = {"calls": count, "cost": round(cost or 0, 4)}

        return {
            "total_calls": total,
            "failures": failures,
            "success_rate": round((total - failures) / total * 100, 1) if total > 0 else 100.0,
            "total_cost_usd": round(total_cost, 4),
            "avg_duration_ms": round(avg_duration) if avg_duration else None,
            "by_agent": breakdown,
        }
