"""WorkflowObserverAgent — daily scan + meta-proposal staging.

The agent loads the org's mute list + persisted thresholds, runs each
unmuted detector over the configured window, dedupes against existing
staged proposals, applies symmetric threshold tuning from recent
corrections, and stages whatever survives via ProposalService.

A single `observer.scan_complete` event closes each org's scan with the
counts and duration so the dashboard can show "last scanned 3h ago".
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, NamedTuple, Protocol, runtime_checkable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_correction import AgentCorrection
from src.models.agent_proposal import (
    STATUS_STAGED,
    AgentProposal,
)
from src.models.org_workflow_config import OrgWorkflowConfig
from src.services.agent_learning_service import AgentLearningService
from src.services.events.actor_factory import actor_agent
from src.services.events.platform_event_service import PlatformEventService
from src.services.proposals import ProposalService

logger = logging.getLogger(__name__)


AGENT_WORKFLOW_OBSERVER = "workflow_observer"
DEFAULT_WINDOW_DAYS = 14
THRESHOLD_FLOOR = 0.0  # detector default acts as the lower bound
THRESHOLD_CEIL = 0.99
THRESHOLD_BUMP = 0.05
ACCEPT_RATE_LOWERING = 0.70
REJECT_RATE_RAISING = 0.30
TUNING_LOOKBACK_DAYS = 30


class DetectorContext(NamedTuple):
    org_id: str
    window_start: datetime
    window_end: datetime
    db: AsyncSession


@dataclass
class MetaProposal:
    """A detector's output. The agent translates this into a
    ProposalService.stage call."""

    detector_id: str
    confidence: float           # 0.0–1.0
    summary: str                # one-sentence human-readable explanation
    evidence: dict              # observed counts/ratios — surfaces on the card
    payload: dict               # creator-shaped (validated downstream)
    entity_type: str = "workflow_config"  # most detectors target this; override in detector


@runtime_checkable
class Detector(Protocol):
    """Each detector implements scan() returning zero or more
    MetaProposals. The harness handles thresholding, deduping, mute-list
    filtering, and staging — detectors only express *what they observed*."""

    detector_id: str
    description: str
    default_threshold: float

    async def scan(self, ctx: DetectorContext) -> list[MetaProposal]: ...


@dataclass
class ScanResult:
    org_id: str
    detectors_run: int
    proposals_staged: int
    proposals_skipped_below_threshold: int = 0
    proposals_skipped_dedup: int = 0
    proposals_skipped_muted: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)


class WorkflowObserverAgent:
    """Phase 6 agent. Iterate detectors → produce MetaProposals → stage
    surviving ones. v1 detector list is wired in
    `src.services.agents.workflow_observer.detectors.DETECTORS`."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.learner = AgentLearningService(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def scan_org(
        self,
        org_id: str,
        *,
        detectors: Iterable[Detector] | None = None,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> ScanResult:
        """Run all unmuted detectors against this org. Returns counts
        suitable for the observer.scan_complete payload."""
        from src.services.agents.workflow_observer.detectors import DETECTORS as _DEFAULT

        active = list(detectors if detectors is not None else _DEFAULT)
        started = time.monotonic()
        result = ScanResult(
            org_id=org_id,
            detectors_run=0,
            proposals_staged=0,
        )

        cfg = await self._get_or_create_config(org_id)
        mutes = cfg.observer_mutes or {}
        thresholds = dict(cfg.observer_thresholds or {})

        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=window_days)
        ctx = DetectorContext(
            org_id=org_id,
            window_start=window_start,
            window_end=window_end,
            db=self.db,
        )

        existing_signatures = await self._load_existing_signatures(org_id)

        for det in active:
            if det.detector_id in mutes:
                result.proposals_skipped_muted += 1
                continue

            # Apply persisted threshold (or seed from default)
            effective_threshold = thresholds.get(
                det.detector_id, det.default_threshold,
            )
            try:
                effective_threshold = await self._tune_threshold(
                    org_id=org_id,
                    detector_id=det.detector_id,
                    detector_default=det.default_threshold,
                    current=effective_threshold,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "workflow_observer: threshold tuning failed for %s: %s",
                    det.detector_id, e,
                )

            thresholds[det.detector_id] = effective_threshold
            result.detectors_run += 1

            try:
                meta_proposals = await det.scan(ctx)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "workflow_observer: detector %s failed for org=%s",
                    det.detector_id, org_id,
                )
                result.errors.append(f"{det.detector_id}: {e}")
                continue

            for mp in meta_proposals:
                if mp.confidence < effective_threshold:
                    result.proposals_skipped_below_threshold += 1
                    continue
                signature = _signature(mp)
                if signature in existing_signatures:
                    result.proposals_skipped_dedup += 1
                    continue
                try:
                    await self._stage(org_id=org_id, mp=mp)
                    existing_signatures.add(signature)
                    result.proposals_staged += 1
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        "workflow_observer: staging failed for %s",
                        det.detector_id,
                    )
                    result.errors.append(f"{det.detector_id} stage: {e}")

        # Persist updated thresholds (tuning may have moved them).
        cfg.observer_thresholds = thresholds
        await self.db.flush()

        result.duration_ms = int((time.monotonic() - started) * 1000)

        # Audit emit — non-blocking.
        try:
            await PlatformEventService.emit(
                db=self.db,
                event_type="observer.scan_complete",
                level="system",
                actor=actor_agent(AGENT_WORKFLOW_OBSERVER),
                organization_id=org_id,
                entity_refs={},
                payload={
                    "detectors_run": result.detectors_run,
                    "proposals_staged": result.proposals_staged,
                    "skipped_below_threshold": result.proposals_skipped_below_threshold,
                    "skipped_dedup": result.proposals_skipped_dedup,
                    "skipped_muted": result.proposals_skipped_muted,
                    "duration_ms": result.duration_ms,
                    "window_days": window_days,
                    "errors": result.errors[:5],
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("observer.scan_complete emit failed: %s", e)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_or_create_config(self, org_id: str) -> OrgWorkflowConfig:
        row = await self.db.get(OrgWorkflowConfig, org_id)
        if row is not None:
            return row
        row = OrgWorkflowConfig(
            organization_id=org_id,
            post_creation_handlers={},
            default_assignee_strategy={"strategy": "last_used_in_org"},
            observer_mutes={},
            observer_thresholds={},
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def _load_existing_signatures(self, org_id: str) -> set[str]:
        """Pull (detector_id, payload-shape) signatures from staged AND
        recently-rejected-permanently proposals so the harness skips
        re-staging the same observation. detector_id is parsed out of
        the persistent `input_context` column (the staging step writes
        it as a leading `[detector_id]` prefix)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        rows = (await self.db.execute(
            select(AgentProposal)
            .where(
                AgentProposal.organization_id == org_id,
                AgentProposal.agent_type == AGENT_WORKFLOW_OBSERVER,
                or_(
                    AgentProposal.status == STATUS_STAGED,
                    AgentProposal.rejected_permanently.is_(True),
                ),
                AgentProposal.created_at >= cutoff,
            )
        )).scalars().all()
        sigs: set[str] = set()
        for r in rows:
            detector_id = _parse_detector_id(r.input_context)
            sigs.add(_payload_signature(
                detector_id, r.entity_type, r.proposed_payload or {},
            ))
        return sigs

    async def _stage(self, *, org_id: str, mp: MetaProposal) -> None:
        """Stage a meta-proposal. The detector_id is encoded into
        input_context (`[detector_id] summary`) so dedup +
        AgentLearningService correction routing can find it later
        without bloating the payload with agent metadata."""
        annotated_summary = f"[{mp.detector_id}] {mp.summary}"

        svc = ProposalService(self.db)
        await svc.stage(
            org_id=org_id,
            agent_type=AGENT_WORKFLOW_OBSERVER,
            entity_type=mp.entity_type,
            source_type="organization",
            source_id=org_id,
            proposed_payload=mp.payload,
            confidence=mp.confidence,
            input_context=annotated_summary,
        )

    async def _tune_threshold(
        self,
        *,
        org_id: str,
        detector_id: str,
        detector_default: float,
        current: float,
    ) -> float:
        """Symmetric snap-back. Read 30d of corrections for this org +
        agent + detector; if reject rate >30%, bump +0.05; if accept rate
        >70%, lower -0.05. Cap at [detector_default, 0.99]. Detector
        default acts as the floor — never go below it."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=TUNING_LOOKBACK_DAYS)
        rows = (await self.db.execute(
            select(AgentCorrection.correction_type, AgentCorrection.input_context)
            .where(
                AgentCorrection.organization_id == org_id,
                AgentCorrection.agent_type == AGENT_WORKFLOW_OBSERVER,
                AgentCorrection.created_at >= cutoff,
            )
        )).all()

        # We tag corrections with the detector_id via input_context's
        # leading "[<detector_id>]" prefix when the harness records them.
        prefix = f"[{detector_id}]"
        relevant = [
            ct for ct, ic in rows
            if (ic or "").startswith(prefix)
        ]
        total = len(relevant)
        if total < 5:
            # Not enough signal — leave threshold where it is.
            return _clamp(current, detector_default, THRESHOLD_CEIL)

        accepts = sum(1 for ct in relevant if ct == "acceptance")
        rejects = sum(1 for ct in relevant if ct == "rejection")
        accept_rate = accepts / total
        reject_rate = rejects / total

        new = current
        if reject_rate > REJECT_RATE_RAISING:
            new = current + THRESHOLD_BUMP
        elif accept_rate > ACCEPT_RATE_LOWERING:
            new = current - THRESHOLD_BUMP
        return _clamp(new, detector_default, THRESHOLD_CEIL)


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _payload_signature(detector_id: str | None, entity_type: str, payload: dict) -> str:
    """Stable fingerprint for dedup. Same detector + same payload shape
    produces the same signature regardless of run timing."""
    serialized = _stable_repr(payload)
    return f"{detector_id or '?'}|{entity_type}|{serialized}"


def _signature(mp: MetaProposal) -> str:
    return _payload_signature(mp.detector_id, mp.entity_type, mp.payload)


def _parse_detector_id(input_context: str | None) -> str | None:
    """Extract the leading `[detector_id]` token written by `_stage`.
    Returns None if no annotation is present (e.g. proposals from other
    agents that happen to share the workflow_observer category in
    AgentCorrection — defensive handling, shouldn't occur in practice)."""
    if not input_context or not input_context.startswith("["):
        return None
    end = input_context.find("]")
    if end <= 1:
        return None
    return input_context[1:end].strip() or None


def _stable_repr(value: Any) -> str:
    """Deterministic string rep — avoids Python's dict-iteration-order
    differences across runs. JSON would also work; keeping this in-house
    so we don't carry the json import for one call."""
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return "{" + ",".join(f"{k}:{_stable_repr(v)}" for k, v in items) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_stable_repr(v) for v in value) + "]"
    return repr(value)
