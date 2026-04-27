"""HandlerMismatchDetector — Phase 6 step 7.

Phase 4 emits two events when a post-creation handler renders:
- `handler.applied` — user engaged + applied the handler.
- `handler.abandoned` — user dismissed without applying.

If the same (entity_type, handler) combination shows ≥70% abandonment
over ≥20 total events in the window, the configured handler is fighting
the user's actual workflow — propose turning it off for that entity_type
by setting `post_creation_handlers[entity_type] = None` (which
WorkflowConfigService.resolve_next_step treats as "no handler").

A future v1.1 detector could propose *switching* to a different handler
based on where the abandoning user navigated next, but v1 only proposes
turn-off — that's the cleanest "stop fighting me" signal.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from src.models.platform_event import PlatformEvent
from src.services.agents.workflow_observer.agent import (
    DetectorContext,
    MetaProposal,
)

logger = logging.getLogger(__name__)


DETECTOR_ID = "handler_mismatch"
MIN_SAMPLE_SIZE = 20
ABANDONMENT_THRESHOLD = 0.70
DEFAULT_CONFIDENCE = 0.80


class HandlerMismatchDetector:
    detector_id = DETECTOR_ID
    description = (
        "When a post-creation handler is dismissed most of the time it "
        "appears, suggest turning it off so it stops getting in the way."
    )
    default_threshold = DEFAULT_CONFIDENCE

    async def scan(self, ctx: DetectorContext) -> list[MetaProposal]:
        rows = (await ctx.db.execute(
            select(PlatformEvent.event_type, PlatformEvent.payload, PlatformEvent.entity_refs)
            .where(
                PlatformEvent.organization_id == ctx.org_id,
                PlatformEvent.event_type.in_(("handler.applied", "handler.abandoned")),
                PlatformEvent.created_at >= ctx.window_start,
                PlatformEvent.created_at < ctx.window_end,
            )
        )).all()

        # Tally per (entity_type, handler).
        applied: dict[tuple[str, str], int] = defaultdict(int)
        abandoned: dict[tuple[str, str], int] = defaultdict(int)
        for event_type, payload, entity_refs in rows:
            payload = payload or {}
            entity_refs = entity_refs or {}
            handler = payload.get("handler")
            entity_type = entity_refs.get("entity_type")
            if not handler or not entity_type:
                continue
            key = (entity_type, handler)
            if event_type == "handler.applied":
                applied[key] += 1
            else:
                abandoned[key] += 1

        proposals: list[MetaProposal] = []
        for key in set(applied) | set(abandoned):
            entity_type, handler = key
            a = applied[key]
            d = abandoned[key]
            total = a + d
            if total < MIN_SAMPLE_SIZE:
                continue
            abandon_rate = d / total
            if abandon_rate < ABANDONMENT_THRESHOLD:
                continue

            confidence = _confidence(abandon_rate, total)
            evidence = {
                "entity_type": entity_type,
                "handler": handler,
                "applied_count": a,
                "abandoned_count": d,
                "total": total,
                "abandon_rate": round(abandon_rate, 3),
                "window_days": (ctx.window_end - ctx.window_start).days,
            }
            summary = (
                f"The {handler} card after creating {entity_type}s was dismissed "
                f"{d} of {total} times in the last {evidence['window_days']} days."
            )
            proposals.append(MetaProposal(
                detector_id=DETECTOR_ID,
                confidence=confidence,
                summary=summary,
                evidence=evidence,
                payload={
                    "target": "post_creation_handlers",
                    "op": "merge",
                    # None tells WorkflowConfigService.resolve_next_step
                    # to fall through with no handler (the falsy branch).
                    "value": {entity_type: None},
                },
                entity_type="workflow_config",
            ))
        return proposals


def _confidence(abandon_rate: float, sample_size: int) -> float:
    """Same shape as DefaultAssignee — rate + sample-size bonus, capped.
    Bonus is smaller because abandonment-pattern truth is noisier than
    assignment patterns (people sometimes skip handlers on purpose for
    one-off jobs that later become rare)."""
    if sample_size < MIN_SAMPLE_SIZE:
        return 0.0
    bonus = 0.003 * max(0, min(50, sample_size - MIN_SAMPLE_SIZE))
    return min(0.99, abandon_rate + bonus)
