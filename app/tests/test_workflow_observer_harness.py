"""Tests for WorkflowObserverAgent — Phase 6 step 5 harness.

Verifies orchestration end-to-end with synthetic detectors so the
detector implementations (steps 6-8) plug into a known-good harness.

Coverage:
- Empty detector list: scan completes, observer.scan_complete fires
  with zero counts, no proposals staged.
- A detector returning above-threshold MetaProposals: each gets staged
  via ProposalService with actor_agent_type=workflow_observer.
- Below-threshold proposals are skipped (counted in result).
- Mute list filters detectors before they run.
- Dedup: re-running with the same detector output produces zero new
  proposals (signature match against existing staged).
- Threshold tuning: ≥5 corrections at >30% reject rate bumps the
  threshold; threshold persists in observer_thresholds.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from src.models.agent_correction import AgentCorrection
from src.models.agent_proposal import AgentProposal
from src.models.org_workflow_config import OrgWorkflowConfig
from src.services.agents.workflow_observer import (
    AGENT_WORKFLOW_OBSERVER,
    DetectorContext,
    MetaProposal,
    WorkflowObserverAgent,
)


# ---------------------------------------------------------------------------
# Synthetic detectors
# ---------------------------------------------------------------------------


@dataclass
class _StaticDetector:
    """Returns a fixed list of MetaProposals — easier to reason about
    than building real platform_events fixtures for every test."""

    detector_id: str
    description: str
    default_threshold: float
    proposals: list[MetaProposal]

    async def scan(self, ctx: DetectorContext) -> list[MetaProposal]:
        return list(self.proposals)


def _mp(detector_id: str, *, confidence: float, value: dict) -> MetaProposal:
    return MetaProposal(
        detector_id=detector_id,
        confidence=confidence,
        summary=f"{detector_id} synthetic",
        evidence={"sample_size": 12},
        payload={
            "target": "default_assignee_strategy",
            "op": "set",
            "value": value,
        },
        entity_type="workflow_config",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_detector_list_scan_completes(db_session, org_a, event_recorder):
    agent = WorkflowObserverAgent(db_session)
    result = await agent.scan_org(org_a.id, detectors=[])
    await db_session.commit()

    assert result.detectors_run == 0
    assert result.proposals_staged == 0
    # Top-level organization_id column is verified separately — the
    # event_recorder's filter is over entity_refs, not top-level cols.
    events = await event_recorder.all_of_type("observer.scan_complete")
    assert len(events) == 1
    assert events[0]["organization_id"] == org_a.id
    assert events[0]["payload"]["detectors_run"] == 0


@pytest.mark.asyncio
async def test_above_threshold_proposal_staged(db_session, org_a):
    detector = _StaticDetector(
        detector_id="default_assignee_test",
        description="synthetic for tests",
        default_threshold=0.80,
        proposals=[
            _mp("default_assignee_test", confidence=0.92,
                value={"strategy": "fixed", "fallback_user_id": str(uuid.uuid4())}),
        ],
    )
    agent = WorkflowObserverAgent(db_session)
    result = await agent.scan_org(org_a.id, detectors=[detector])
    await db_session.commit()

    assert result.proposals_staged == 1
    # Verify a real AgentProposal row landed.
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(AgentProposal).where(
            AgentProposal.organization_id == org_a.id,
            AgentProposal.agent_type == AGENT_WORKFLOW_OBSERVER,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_type == "workflow_config"
    # detector_id is encoded into input_context as `[detector_id] summary`.
    assert rows[0].input_context.startswith("[default_assignee_test]")


@pytest.mark.asyncio
async def test_below_threshold_skipped(db_session, org_a):
    detector = _StaticDetector(
        detector_id="below_threshold_test",
        description="synthetic",
        default_threshold=0.80,
        proposals=[
            _mp("below_threshold_test", confidence=0.65,
                value={"strategy": "fixed", "fallback_user_id": str(uuid.uuid4())}),
        ],
    )
    agent = WorkflowObserverAgent(db_session)
    result = await agent.scan_org(org_a.id, detectors=[detector])
    await db_session.commit()

    assert result.proposals_staged == 0
    assert result.proposals_skipped_below_threshold == 1


@pytest.mark.asyncio
async def test_mute_list_skips_detector(db_session, org_a):
    cfg = OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={},
        default_assignee_strategy={"strategy": "last_used_in_org"},
        observer_mutes={"muted_detector": {"muted_at": "2026-01-01T00:00:00Z"}},
        observer_thresholds={},
    )
    db_session.add(cfg)
    await db_session.commit()

    detector = _StaticDetector(
        detector_id="muted_detector",
        description="synthetic",
        default_threshold=0.80,
        proposals=[
            _mp("muted_detector", confidence=0.99,
                value={"strategy": "fixed", "fallback_user_id": str(uuid.uuid4())}),
        ],
    )
    agent = WorkflowObserverAgent(db_session)
    result = await agent.scan_org(org_a.id, detectors=[detector])
    await db_session.commit()

    assert result.detectors_run == 0  # muted before running
    assert result.proposals_skipped_muted == 1
    assert result.proposals_staged == 0


@pytest.mark.asyncio
async def test_dedup_skips_existing_signature(db_session, org_a):
    user_id_value = str(uuid.uuid4())
    detector = _StaticDetector(
        detector_id="dedup_test",
        description="synthetic",
        default_threshold=0.80,
        proposals=[
            _mp("dedup_test", confidence=0.92,
                value={"strategy": "fixed", "fallback_user_id": user_id_value}),
        ],
    )
    agent = WorkflowObserverAgent(db_session)

    # First scan: stages.
    r1 = await agent.scan_org(org_a.id, detectors=[detector])
    await db_session.commit()
    assert r1.proposals_staged == 1

    # Second scan: same detector, same payload — must dedup.
    r2 = await agent.scan_org(org_a.id, detectors=[detector])
    await db_session.commit()
    assert r2.proposals_staged == 0
    assert r2.proposals_skipped_dedup == 1


@pytest.mark.asyncio
async def test_threshold_tuning_bumps_on_rejection_pressure(db_session, org_a):
    """≥5 corrections, >30% rejection rate → threshold bumps +0.05.
    Verify the new threshold persists on org_workflow_config."""
    # Seed 6 corrections: 5 rejections, 1 acceptance — 83% reject rate.
    for i in range(5):
        db_session.add(AgentCorrection(
            id=str(uuid.uuid4()),
            organization_id=org_a.id,
            agent_type=AGENT_WORKFLOW_OBSERVER,
            correction_type="rejection",
            input_context="[tuning_test] synthetic",
        ))
    db_session.add(AgentCorrection(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        agent_type=AGENT_WORKFLOW_OBSERVER,
        correction_type="acceptance",
        category="x",  # so record_correction's signal-skip doesn't drop it
        input_context="[tuning_test] synthetic",
    ))
    await db_session.commit()

    detector = _StaticDetector(
        detector_id="tuning_test",
        description="synthetic",
        default_threshold=0.80,
        # Confidence 0.83 — passes default but should fail bumped 0.85.
        proposals=[
            _mp("tuning_test", confidence=0.83,
                value={"strategy": "fixed", "fallback_user_id": str(uuid.uuid4())}),
        ],
    )
    agent = WorkflowObserverAgent(db_session)
    result = await agent.scan_org(org_a.id, detectors=[detector])
    await db_session.commit()

    # Threshold raised to 0.85 → proposal at 0.83 falls below.
    assert result.proposals_skipped_below_threshold == 1
    assert result.proposals_staged == 0

    cfg = await db_session.get(OrgWorkflowConfig, org_a.id)
    assert cfg.observer_thresholds.get("tuning_test") == pytest.approx(0.85, abs=1e-6)
