"""Activation-funnel event emission.

Emits one event per org per milestone, the first time that milestone is hit.
Backend-derived from the triggering record's creation — the user doesn't
click "mark me activated," we observe it.

Events (docs/event-taxonomy.md §8.13):
  activation.account_created        — first user registered for the org
  activation.first_customer_added   — first customer
  activation.first_visit_completed  — first visit completed
  activation.first_invoice_sent     — first invoice sent (not estimate)
  activation.first_payment_received — first payment recorded
  activation.first_ai_proposal_accepted — Phase 2 (proposals system not built)

Payload: each event carries `minutes_since_prior_milestone` so Sonar can
reconstruct the funnel as a sequence of durations, plus `source` for
context.

First-per-org-ever enforcement: check `platform_events` for an existing
event of the same type + org; if present, no-op. Race window (two
concurrent "first X" creates) is acceptable per our rare-duplicates
philosophy. At scale this check is cheap thanks to the
(organization_id, created_at desc) index + level/event_type filter.

Design reference: docs/ai-platform-phase-1.md §6.12.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.actor_factory import actor_system
from src.services.events.platform_event_service import Actor, PlatformEventService

logger = logging.getLogger(__name__)


ActivationEventType = Literal[
    "activation.account_created",
    "activation.first_customer_added",
    "activation.first_visit_completed",
    "activation.first_invoice_sent",
    "activation.first_payment_received",
    "activation.first_ai_proposal_accepted",
]


# Ordered list — defines the canonical funnel sequence so the tracker can
# compute "minutes_since_prior_milestone" by looking up the most recent
# milestone BEFORE this one that has already fired.
FUNNEL_ORDER: tuple[ActivationEventType, ...] = (
    "activation.account_created",
    "activation.first_customer_added",
    "activation.first_visit_completed",
    "activation.first_invoice_sent",
    "activation.first_payment_received",
    "activation.first_ai_proposal_accepted",
)


async def _has_fired(db: AsyncSession, event_type: str, org_id: str) -> bool:
    """Check if this activation event has already fired for this org."""
    try:
        result = await db.execute(
            text(
                "SELECT 1 FROM platform_events "
                "WHERE event_type = :etype AND organization_id = :org "
                "LIMIT 1"
            ),
            {"etype": event_type, "org": org_id},
        )
        return result.first() is not None
    except Exception as e:
        # Defensive: if the check itself fails, don't block the business
        # operation. Log and assume it hasn't fired — worst case we emit a
        # duplicate activation event, which downstream consumers should be
        # robust to.
        logger.error(
            "activation.has_fired_check failed", extra={"event_type": event_type, "error": str(e)[:200]}
        )
        return False


async def _prior_milestone_time(
    db: AsyncSession, event_type: ActivationEventType, org_id: str
) -> Optional[str]:
    """Return the created_at (ISO string) of the most recent activation
    milestone that fired BEFORE this one in the funnel order, for this org.
    Used to compute `minutes_since_prior_milestone` in the payload.
    Returns None for the first milestone (account_created) or if no prior
    milestone has fired."""
    try:
        idx = FUNNEL_ORDER.index(event_type)
    except ValueError:
        return None
    if idx == 0:
        return None

    # Look up the MOST RECENT prior milestone (any in the funnel before this).
    prior_types = list(FUNNEL_ORDER[:idx])
    try:
        result = await db.execute(
            text(
                "SELECT created_at FROM platform_events "
                "WHERE organization_id = :org AND event_type = ANY(:types) "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"org": org_id, "types": prior_types},
        )
        row = result.first()
        return row[0].isoformat() if row else None
    except Exception as e:
        logger.error(
            "activation.prior_milestone_lookup failed",
            extra={"event_type": event_type, "error": str(e)[:200]},
        )
        return None


async def emit_if_first(
    db: AsyncSession,
    event_type: ActivationEventType,
    *,
    organization_id: str,
    entity_refs: Optional[dict] = None,
    source: Optional[str] = None,
    actor: Optional[Actor] = None,
) -> bool:
    """Emit the activation event only if it hasn't fired for this org yet.

    Returns True if emitted, False if this milestone already fired for
    this org (no-op).

    Never raises — wraps everything in the same fail-soft contract
    as PlatformEventService.emit.
    """
    try:
        if not organization_id:
            return False  # Platform-scoped activation events aren't a thing
        if await _has_fired(db, event_type, organization_id):
            return False

        # Compute time-since-prior-milestone for the funnel chart.
        prior_iso = await _prior_milestone_time(db, event_type, organization_id)
        payload: dict = {}
        if source:
            payload["source"] = source
        if prior_iso:
            from datetime import datetime, timezone
            try:
                prior_dt = datetime.fromisoformat(prior_iso)
                if prior_dt.tzinfo is None:
                    prior_dt = prior_dt.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - prior_dt
                payload["minutes_since_prior_milestone"] = int(delta.total_seconds() / 60)
            except Exception:
                pass

        await PlatformEventService.emit(
            db=db,
            event_type=event_type,
            level="user_action" if actor and actor.actor_type == "user" else "system_action",
            actor=actor or actor_system(),
            organization_id=organization_id,
            entity_refs=entity_refs or {},
            payload=payload,
        )
        return True
    except Exception as e:
        logger.error(
            "activation.emit_if_first failed",
            extra={"event_type": event_type, "error": str(e)[:200]},
        )
        return False
