"""DefaultAssigneeDetector — Phase 6 step 6.

Observes AgentAction (job) creations in the window. If ≥80% of jobs go
to the same assignee with ≥10 sample size, proposes the org switch
their default_assignee_strategy from `last_used_in_org` (the dynamic
default that bounces with each new assignment) to `fixed` with that
user as the fallback (predictable, durable).

Why AgentAction, not platform_events: the assignee column is the direct
ground truth. Going through `proposal.accepted` events would only
capture proposal-sourced jobs, missing manual creates — and the org's
actual assignment pattern is what should drive the suggestion,
regardless of how the job was created.

assigned_to is a string column carrying either a first_name (legacy
shape used by the inline picker) or a user_id (newer code paths). The
detector treats both — first_name lookups go through OrganizationUser
+ User to resolve to a user_id before staging.
"""

from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy import select

from src.models.agent_action import AgentAction
from src.models.organization_user import OrganizationUser
from src.models.user import User
from src.services.agents.workflow_observer.agent import (
    DetectorContext,
    MetaProposal,
)

logger = logging.getLogger(__name__)


DETECTOR_ID = "default_assignee"
MIN_SAMPLE_SIZE = 10
DOMINANCE_THRESHOLD = 0.80
DEFAULT_CONFIDENCE = 0.80


class DefaultAssigneeDetector:
    detector_id = DETECTOR_ID
    description = (
        "When most new jobs in your org go to the same person, suggest "
        "making them the default assignee for new jobs."
    )
    default_threshold = DEFAULT_CONFIDENCE

    async def scan(self, ctx: DetectorContext) -> list[MetaProposal]:
        rows = (await ctx.db.execute(
            select(AgentAction.assigned_to)
            .where(
                AgentAction.organization_id == ctx.org_id,
                AgentAction.created_at >= ctx.window_start,
                AgentAction.created_at < ctx.window_end,
                AgentAction.assigned_to.is_not(None),
                AgentAction.assigned_to != "unassigned",
            )
        )).all()
        assignments = [r[0] for r in rows if r[0]]

        if len(assignments) < MIN_SAMPLE_SIZE:
            return []

        counts = Counter(assignments)
        dominant_value, dominant_count = counts.most_common(1)[0]
        ratio = dominant_count / len(assignments)
        if ratio < DOMINANCE_THRESHOLD:
            return []

        # Map dominant_value (first_name OR user_id) to user_id.
        user_id = await _resolve_user_id(
            ctx.db, ctx.org_id, dominant_value,
        )
        if user_id is None:
            # Couldn't resolve — skip silently. Surfacing an unresolvable
            # name as a proposal would just confuse the admin.
            logger.info(
                "default_assignee: dominant value %r couldn't be resolved "
                "to a user_id (org=%s) — skipping",
                dominant_value, ctx.org_id,
            )
            return []

        # If org's current strategy is already `fixed` with this same
        # fallback, the harness's dedup will skip this on stage. The
        # detector still produces it — it's the harness's job to decide.

        confidence = _confidence(ratio, len(assignments))
        evidence = {
            "sample_size": len(assignments),
            "dominant_count": dominant_count,
            "ratio": round(ratio, 3),
            "window_days": (ctx.window_end - ctx.window_start).days,
        }
        summary = (
            f"{dominant_count} of {len(assignments)} jobs over the last "
            f"{evidence['window_days']} days went to the same person."
        )
        return [MetaProposal(
            detector_id=DETECTOR_ID,
            confidence=confidence,
            summary=summary,
            evidence=evidence,
            payload={
                "target": "default_assignee_strategy",
                "op": "set",
                "value": {"strategy": "fixed", "fallback_user_id": user_id},
            },
            entity_type="workflow_config",
        )]


async def _resolve_user_id(db, org_id: str, value: str) -> str | None:
    """Map an `assigned_to` string to a User.id.

    Three cases:
    1. value already looks like a UUID → return as-is (assumes membership;
       caller may want to verify, but the agent only stages — accept-time
       validation through WorkflowConfigService catches stale ids).
    2. value matches a user's first_name in this org → return that user_id.
    3. nothing matches → None.
    """
    if _looks_like_uuid(value):
        return value
    row = (await db.execute(
        select(User.id)
        .join(OrganizationUser, OrganizationUser.user_id == User.id)
        .where(
            OrganizationUser.organization_id == org_id,
            User.first_name == value,
            User.is_active == True,  # noqa: E712
        )
        .limit(1)
    )).first()
    return row[0] if row else None


def _looks_like_uuid(value: str) -> bool:
    return len(value) == 36 and value.count("-") == 4


def _confidence(ratio: float, sample_size: int) -> float:
    """Confidence equals dominance ratio once past the sample-size gate.
    Adds a small sample-size bonus so boundary ratios with large N
    pass cleanly. Capped at 0.99 (the harness ceiling).

    Examples: ratio=0.80, N=10 → 0.80 (just at default threshold);
              ratio=0.80, N=50 → 0.85 (sample-size bonus kicks in);
              ratio=0.95, N=20 → 0.95 (rounded);
              ratio=0.95, N=100 → 0.99 (capped)."""
    if sample_size < MIN_SAMPLE_SIZE:
        return 0.0
    bonus = 0.005 * max(0, min(40, sample_size - MIN_SAMPLE_SIZE))
    return min(0.99, ratio + bonus)
