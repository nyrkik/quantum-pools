"""ProposalService — state machine for `agent_proposals`.

Every AI suggestion flows through here. The service is the SINGLE
canonical path for staging, accepting, editing, rejecting, superseding,
and expiring proposals. Direct inserts into `agent_proposals` from
anywhere else are a bug.

Every resolve method:
1. Transitions proposal status.
2. Atomically writes an `agent_corrections` row via AgentLearningService
   (enforces DNA rule #2 — every agent learns).
3. Emits the corresponding `proposal.*` platform event.
4. Invokes an entity creator where applicable (accept/edit_and_accept).

All transitions live in one transaction: if the creator raises, the
proposal stays `staged` (no half-complete state).

See `docs/ai-platform-phase-2.md` for the full contract.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_proposal import (
    AgentProposal,
    STATUS_STAGED,
    STATUS_ACCEPTED,
    STATUS_EDITED,
    STATUS_REJECTED,
    STATUS_EXPIRED,
    STATUS_SUPERSEDED,
    TERMINAL_STATUSES,
)
from src.services.events.platform_event_service import (
    Actor,
    PlatformEventService,
    actor_system,
)
from src.services.proposals.json_patch import make_patch
from src.services.proposals.registry import get_entry

logger = logging.getLogger(__name__)


# --- Proposal burst-detection ---------------------------------------------
#
# Per-(agent_type, org) stage count in a rolling hour. If it crosses
# BURST_THRESHOLD, we emit a warning + ntfy alert. We do NOT hard-block
# — data-capture-is-king — a bad run should surface, not get throttled
# away (see feedback_data_capture_is_king.md).
BURST_WINDOW = timedelta(hours=1)
BURST_THRESHOLD = 200


class ProposalConflictError(Exception):
    """Raised when a creator signals 'target already exists / superseded
    by user action.' Handled by accept() as a soft-reject."""


class ProposalStateError(Exception):
    """Caller tried to transition a proposal that isn't in `staged`."""


class ProposalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    async def _load(self, proposal_id: str) -> AgentProposal:
        p = await self.db.get(AgentProposal, proposal_id)
        if not p:
            raise LookupError(f"Proposal {proposal_id} not found")
        return p

    async def _require_staged(self, p: AgentProposal) -> None:
        if p.status != STATUS_STAGED:
            raise ProposalStateError(
                f"Proposal {p.id} is {p.status!r} (must be {STATUS_STAGED!r} to resolve)"
            )

    async def _record_correction(
        self,
        *,
        org_id: str,
        agent_type: str,
        correction_type: str,     # "acceptance" | "edit" | "rejection"
        entity_type: str,
        original_payload: dict,
        corrected_payload: Optional[dict],
        input_context: Optional[str],
        customer_id: Optional[str],
        source_id: Optional[str],
    ) -> None:
        """Write to agent_corrections — the learning-loop bridge.

        Wrapped in a SAVEPOINT (`begin_nested`) so a failure here (e.g.,
        stale customer_id → FK violation) doesn't poison the outer
        transaction. Learning is non-critical to correctness of the
        proposal state machine — a missed correction is a missed lesson,
        not a bug in the resolution.
        """
        try:
            from src.services.agent_learning_service import AgentLearningService
            import json as _json
            async with self.db.begin_nested():
                learner = AgentLearningService(self.db)
                await learner.record_correction(
                    org_id=org_id,
                    agent_type=agent_type,
                    correction_type=correction_type,
                    original_output=_json.dumps(original_payload),
                    corrected_output=_json.dumps(corrected_payload) if corrected_payload else None,
                    input_context=input_context,
                    category=entity_type,  # coarse category = entity_type
                    customer_id=customer_id,
                    source_id=source_id,
                    source_type="agent_proposal",
                )
        except Exception as e:  # noqa: BLE001
            # Savepoint auto-rolled back; outer txn unaffected.
            logger.error("record_correction failed for proposal: %s", e)

    async def _emit(
        self,
        event_type: str,
        p: AgentProposal,
        *,
        actor: Actor,
        extra_payload: Optional[dict] = None,
    ) -> None:
        """Emit a `proposal.*` event. Fail-soft (the service already
        does, this is belt-and-suspenders)."""
        refs: dict = {"agent_proposal_id": p.id}
        if p.source_id:
            refs["source_id"] = p.source_id
        # Outcome entity reference when resolved
        if p.outcome_entity_id and p.outcome_entity_type:
            refs[f"{p.outcome_entity_type}_id"] = p.outcome_entity_id

        payload: dict = {
            "agent_type": p.agent_type,
            "entity_type": p.entity_type,
            "source_type": p.source_type,
        }
        if p.confidence is not None:
            payload["confidence"] = p.confidence
        if extra_payload:
            payload.update(extra_payload)

        await PlatformEventService.emit(
            db=self.db,
            event_type=event_type,
            level="user_action" if actor.actor_type == "user" else (
                "agent_action" if actor.actor_type == "agent" else "system_action"
            ),
            actor=actor,
            organization_id=p.organization_id,
            entity_refs=refs,
            payload=payload,
        )

    async def _check_burst(self, agent_type: str, org_id: str) -> None:
        """Fire a ntfy alert if a single agent has staged >BURST_THRESHOLD
        proposals for one org within BURST_WINDOW. No hard block."""
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - BURST_WINDOW
        count = (await self.db.execute(
            select(func.count(AgentProposal.id)).where(
                AgentProposal.organization_id == org_id,
                AgentProposal.agent_type == agent_type,
                AgentProposal.created_at >= cutoff,
            )
        )).scalar() or 0
        if count >= BURST_THRESHOLD:
            logger.warning(
                "proposal_burst agent=%s org=%s count_in_hour=%d",
                agent_type, org_id, count,
            )
            try:
                from src.utils.notify import send_ntfy
                send_ntfy(
                    title="QP proposal burst",
                    body=(
                        f"agent={agent_type} org={org_id} "
                        f"staged {count} proposals in last hour (>={BURST_THRESHOLD}). "
                        f"Possible runaway agent — investigate."
                    ),
                    priority="high",
                    tags="warning",
                    cooldown_key=f"proposal_burst_{agent_type}_{org_id}",
                    cooldown_seconds=3600,
                )
            except Exception:
                pass  # alert is best-effort

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def stage(
        self,
        *,
        org_id: str,
        agent_type: str,
        entity_type: str,
        source_type: str,
        source_id: Optional[str],
        proposed_payload: dict,
        confidence: Optional[float] = None,
        input_context: Optional[str] = None,
        actor: Optional[Actor] = None,
    ) -> AgentProposal:
        """Stage a new proposal.

        Validates entity_type + payload shape upfront. Unknown entity_type
        raises immediately (programmer error; no fallback). Invalid
        payload raises (AI bug; surface it).
        """
        entry = get_entry(entity_type)  # raises KeyError on unknown

        # Stage-time payload validation — catch malformed AI output here,
        # not at accept time.
        if entry.schema is not None:
            validated = entry.schema.model_validate(proposed_payload)
            proposed_payload = validated.model_dump(mode="json")

        p = AgentProposal(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            agent_type=agent_type,
            entity_type=entity_type,
            source_type=source_type,
            source_id=source_id,
            proposed_payload=proposed_payload,
            confidence=confidence,
            status=STATUS_STAGED,
        )
        # Stash input_context on the model via a transient attr — we use
        # it on resolve to feed the learning signal. Not persisted.
        p._input_context = input_context  # type: ignore[attr-defined]

        self.db.add(p)
        await self.db.flush()

        # Event first (part of the same transaction).
        await self._emit(
            "proposal.staged", p,
            actor=actor or actor_system(),
        )

        # Burst alert AFTER the insert (count includes this row — the
        # threshold is the stage count in the past hour INCLUDING this one).
        await self._check_burst(agent_type, org_id)

        return p

    async def accept(
        self,
        *,
        proposal_id: str,
        actor: Actor,
    ) -> tuple[AgentProposal, Any]:
        """Accept unchanged → create entity, mark accepted, write learning,
        emit event. Single transaction: creator failure rolls everything
        back, proposal stays staged."""
        p = await self._load(proposal_id)
        await self._require_staged(p)

        entry = get_entry(p.entity_type)

        # Run the creator. Any exception propagates → transaction rolls back.
        try:
            created = await entry.creator(
                p.proposed_payload, p.organization_id, actor, self.db,
            )
        except ProposalConflictError:
            # Creator signaled "user already did this" — soft-reject.
            return await self._reject_as_conflict(p, actor)

        # Pull the id off the created object. Most domain entities have .id.
        outcome_id = getattr(created, "id", None)
        if outcome_id is None and isinstance(created, dict):
            outcome_id = created.get("id")

        p.status = STATUS_ACCEPTED
        p.outcome_entity_type = entry.outcome_entity_type
        p.outcome_entity_id = outcome_id
        p.resolved_at = datetime.now(timezone.utc)
        p.resolved_by_user_id = actor.user_id if actor.actor_type == "user" else None
        await self.db.flush()

        await self._record_correction(
            org_id=p.organization_id,
            agent_type=p.agent_type,
            correction_type="acceptance",
            entity_type=p.entity_type,
            original_payload=p.proposed_payload,
            corrected_payload=None,
            input_context=getattr(p, "_input_context", None),
            customer_id=self._extract_customer_id(p.proposed_payload),
            source_id=p.id,
        )

        await self._emit("proposal.accepted", p, actor=actor)

        return p, created

    async def edit_and_accept(
        self,
        *,
        proposal_id: str,
        actor: Actor,
        edited_payload: dict,
        note: Optional[str] = None,
    ) -> tuple[AgentProposal, Any]:
        """Human edited the proposal's draft before accepting. Compute
        RFC 6902 patch as `user_delta`, record learning with edit_type,
        run creator with the edited payload."""
        p = await self._load(proposal_id)
        await self._require_staged(p)

        entry = get_entry(p.entity_type)

        # Validate edited payload same way we validate stage-time payload.
        if entry.schema is not None:
            validated = entry.schema.model_validate(edited_payload)
            edited_payload = validated.model_dump(mode="json")

        # Minimal JSON patch recording exactly what the human changed.
        patch = make_patch(p.proposed_payload, edited_payload)

        try:
            created = await entry.creator(
                edited_payload, p.organization_id, actor, self.db,
            )
        except ProposalConflictError:
            return await self._reject_as_conflict(p, actor)

        outcome_id = getattr(created, "id", None)
        if outcome_id is None and isinstance(created, dict):
            outcome_id = created.get("id")

        p.status = STATUS_EDITED
        p.outcome_entity_type = entry.outcome_entity_type
        p.outcome_entity_id = outcome_id
        p.user_delta = patch
        p.resolution_note = note
        p.resolved_at = datetime.now(timezone.utc)
        p.resolved_by_user_id = actor.user_id if actor.actor_type == "user" else None
        await self.db.flush()

        await self._record_correction(
            org_id=p.organization_id,
            agent_type=p.agent_type,
            correction_type="edit",
            entity_type=p.entity_type,
            original_payload=p.proposed_payload,
            corrected_payload=edited_payload,
            input_context=getattr(p, "_input_context", None),
            customer_id=self._extract_customer_id(edited_payload),
            source_id=p.id,
        )

        await self._emit(
            "proposal.edited", p,
            actor=actor,
            extra_payload={"delta_op_count": len(patch)},
        )

        return p, created

    async def reject(
        self,
        *,
        proposal_id: str,
        actor: Actor,
        permanently: bool = False,
        note: Optional[str] = None,
    ) -> AgentProposal:
        """Reject. `permanently=True` adds a strong learning signal
        ("never propose this pattern again") without hard-blocking
        re-proposals (lessons > brittle rules; see spec §5.3)."""
        p = await self._load(proposal_id)
        await self._require_staged(p)

        p.status = STATUS_REJECTED
        p.rejected_permanently = permanently
        p.resolution_note = note
        p.resolved_at = datetime.now(timezone.utc)
        p.resolved_by_user_id = actor.user_id if actor.actor_type == "user" else None
        await self.db.flush()

        await self._record_correction(
            org_id=p.organization_id,
            agent_type=p.agent_type,
            correction_type="rejection",
            entity_type=p.entity_type,
            original_payload=p.proposed_payload,
            corrected_payload=None,
            input_context=getattr(p, "_input_context", None),
            customer_id=self._extract_customer_id(p.proposed_payload),
            source_id=p.id,
        )

        event_type = "proposal.rejected_permanently" if permanently else "proposal.rejected"
        await self._emit(
            event_type, p,
            actor=actor,
            extra_payload={"note": note, "permanently": permanently},
        )

        return p

    async def _reject_as_conflict(
        self, p: AgentProposal, actor: Actor,
    ) -> tuple[AgentProposal, None]:
        """Creator signaled the target entity already exists (user
        manually created in the meantime). Auto-reject with conflict
        reason so the UX shows a clear 'user_created_already.'"""
        p.status = STATUS_REJECTED
        p.resolution_note = "superseded_by_user_action"
        p.resolved_at = datetime.now(timezone.utc)
        p.resolved_by_user_id = actor.user_id if actor.actor_type == "user" else None
        await self.db.flush()

        await self._record_correction(
            org_id=p.organization_id,
            agent_type=p.agent_type,
            correction_type="rejection",
            entity_type=p.entity_type,
            original_payload=p.proposed_payload,
            corrected_payload=None,
            input_context=getattr(p, "_input_context", None),
            customer_id=self._extract_customer_id(p.proposed_payload),
            source_id=p.id,
        )

        await self._emit(
            "proposal.rejected", p,
            actor=actor,
            extra_payload={"reason": "user_created_already"},
        )
        return p, None

    async def supersede(
        self,
        *,
        old_proposal_id: str,
        new_payload: dict,
        new_confidence: Optional[float] = None,
        actor: Optional[Actor] = None,
    ) -> AgentProposal:
        """Agent re-proposed on fresher context. Old proposal becomes
        `superseded`, new one stages. No learning record for the old —
        user didn't act on it, no signal."""
        old = await self._load(old_proposal_id)
        await self._require_staged(old)

        # New proposal inherits source + agent + entity from old.
        new = await self.stage(
            org_id=old.organization_id,
            agent_type=old.agent_type,
            entity_type=old.entity_type,
            source_type=old.source_type,
            source_id=old.source_id,
            proposed_payload=new_payload,
            confidence=new_confidence,
            actor=actor,
        )

        # Link + mark old. Note: stage() already flushed the new row,
        # so new.id is populated.
        old.status = STATUS_SUPERSEDED
        old.superseded_by_id = new.id
        old.resolved_at = datetime.now(timezone.utc)
        await self.db.flush()

        await self._emit(
            "proposal.superseded", old,
            actor=actor or actor_system(),
            extra_payload={"superseded_by_id": new.id},
        )

        return new

    async def expire_stale(self, age_days: int = 30) -> int:
        """APScheduler entry point — mark staged proposals older than
        `age_days` as expired. Emits per-row `proposal.expired` +
        records a rejection-class learning signal."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=age_days)

        result = await self.db.execute(
            select(AgentProposal).where(
                AgentProposal.status == STATUS_STAGED,
                AgentProposal.created_at < cutoff,
            )
        )
        stale = result.scalars().all()

        for p in stale:
            p.status = STATUS_EXPIRED
            p.resolved_at = datetime.now(timezone.utc)
            p.resolution_note = "auto_expired"
        await self.db.flush()

        for p in stale:
            await self._record_correction(
                org_id=p.organization_id,
                agent_type=p.agent_type,
                correction_type="rejection",
                entity_type=p.entity_type,
                original_payload=p.proposed_payload,
                corrected_payload=None,
                input_context=None,
                customer_id=self._extract_customer_id(p.proposed_payload),
                source_id=p.id,
            )
            await self._emit(
                "proposal.expired", p,
                actor=actor_system(),
                extra_payload={"age_days": age_days},
            )

        return len(stale)

    # -----------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_customer_id(payload: dict) -> Optional[str]:
        """Best-effort: many proposal payloads include customer_id. Used
        to scope the learning record so lessons are customer-specific
        when applicable."""
        return payload.get("customer_id") if isinstance(payload, dict) else None
