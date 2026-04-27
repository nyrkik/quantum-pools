"""ClassificationOverrideDetector — Phase 6 step 8.

Watches `thread.category_changed` events (emitted when a user overrides
the AI classifier's category on a thread) and clusters them by sender
domain. If the same `(from_category, to_category, sender_domain)` triple
appears ≥5 times in the window, the AI is consistently misclassifying
mail from that domain and the user keeps fixing it — propose an
inbox_rule that auto-categorizes future mail from that sender.

Event payload from event-taxonomy.md:
    thread.category_changed → entity_refs.thread_id, payload: {from, to}

The detector joins thread_id → AgentThread.contact_email to get the
sender, extracts the domain, and groups.

Per the spec, the detector emits an `inbox_rule` entity_type proposal,
not `workflow_config` — the right artifact is a real rule the
InboxRulesService can evaluate at ingest time. The MVP inbox_rule
creator (step 3) handles validation + insertion on accept.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import select

from src.models.agent_thread import AgentThread
from src.models.platform_event import PlatformEvent
from src.services.agents.workflow_observer.agent import (
    DetectorContext,
    MetaProposal,
)

logger = logging.getLogger(__name__)


DETECTOR_ID = "classification_override"
MIN_CLUSTER_SIZE = 5
DEFAULT_CONFIDENCE = 0.80


class ClassificationOverrideDetector:
    detector_id = DETECTOR_ID
    description = (
        "When the AI keeps misclassifying mail from the same sender and "
        "you keep fixing it, suggest a rule that auto-categorizes future "
        "mail from that sender."
    )
    default_threshold = DEFAULT_CONFIDENCE

    async def scan(self, ctx: DetectorContext) -> list[MetaProposal]:
        # Pull category-change events with their thread_id refs.
        rows = (await ctx.db.execute(
            select(PlatformEvent.payload, PlatformEvent.entity_refs)
            .where(
                PlatformEvent.organization_id == ctx.org_id,
                PlatformEvent.event_type == "thread.category_changed",
                PlatformEvent.created_at >= ctx.window_start,
                PlatformEvent.created_at < ctx.window_end,
            )
        )).all()
        if not rows:
            return []

        thread_ids: set[str] = set()
        events: list[tuple[str, str, str]] = []  # (thread_id, from_cat, to_cat)
        for payload, refs in rows:
            payload = payload or {}
            refs = refs or {}
            thread_id = refs.get("thread_id")
            from_cat = payload.get("from")
            to_cat = payload.get("to")
            if not thread_id or not from_cat or not to_cat or from_cat == to_cat:
                continue
            thread_ids.add(thread_id)
            events.append((thread_id, from_cat, to_cat))
        if not events:
            return []

        # Resolve thread_id → contact_email in one query.
        thread_rows = (await ctx.db.execute(
            select(AgentThread.id, AgentThread.contact_email)
            .where(AgentThread.id.in_(thread_ids))
        )).all()
        email_by_thread = {tid: email for tid, email in thread_rows if email}

        # Cluster by (from_cat, to_cat, sender_domain).
        clusters: dict[tuple[str, str, str], int] = defaultdict(int)
        for thread_id, from_cat, to_cat in events:
            email = email_by_thread.get(thread_id)
            if not email:
                continue
            domain = _extract_domain(email)
            if not domain:
                continue
            clusters[(from_cat, to_cat, domain)] += 1

        proposals: list[MetaProposal] = []
        for (from_cat, to_cat, domain), count in clusters.items():
            if count < MIN_CLUSTER_SIZE:
                continue
            confidence = _confidence(count)
            window_days = (ctx.window_end - ctx.window_start).days
            evidence = {
                "from_category": from_cat,
                "to_category": to_cat,
                "sender_domain": domain,
                "count": count,
                "window_days": window_days,
            }
            summary = (
                f"You changed {count} threads from {domain} from "
                f"\"{from_cat}\" to \"{to_cat}\" in the last {window_days} days."
            )
            proposals.append(MetaProposal(
                detector_id=DETECTOR_ID,
                confidence=confidence,
                summary=summary,
                evidence=evidence,
                payload={
                    "name": f"Auto-categorize {domain} as {to_cat}",
                    "conditions": [{
                        "field": "sender_domain",
                        "operator": "equals",
                        "value": domain,
                    }],
                    "actions": [{
                        "type": "assign_category",
                        "params": {"category": to_cat},
                    }],
                    "is_active": True,
                },
                entity_type="inbox_rule",
            ))
        return proposals


def _extract_domain(email: str) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain or None


def _confidence(count: int) -> float:
    """Confidence climbs slowly with cluster size. At the floor (5
    overrides) the detector is just at default threshold (0.80); each
    additional override adds 0.02 up to a 0.99 cap. Reflects that
    cluster size IS the trustworthiness signal here — there's no
    separate ratio dimension."""
    if count < MIN_CLUSTER_SIZE:
        return 0.0
    base = 0.80
    bonus = 0.02 * max(0, min(20, count - MIN_CLUSTER_SIZE))
    return min(0.99, base + bonus)
