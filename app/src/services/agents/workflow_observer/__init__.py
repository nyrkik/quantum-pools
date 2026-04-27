"""WorkflowObserverAgent — Phase 6 of the AI Platform plan.

Daily per-org scan over the last N days of platform_events +
agent_proposals outcomes. Each registered detector returns zero or
more MetaProposal records; the agent stages them via ProposalService
where the rest of the platform (proposal card UI, AgentLearningService)
treats them like any other proposal.

The agent owns:
- The scan harness (window calculation, mute-list filter, dedup against
  existing staged proposals, threshold persistence).
- Symmetric self-tuning: `_apply_threshold_tuning` reads recent
  workflow_observer corrections via AgentLearningService and bumps each
  detector's confidence threshold based on accept/reject ratios.
- The `observer.scan_complete` event emit.

Detector implementations live in sibling modules and are wired into
DETECTORS at the bottom of this file. v1 ships three; the protocol is
extensible without touching the harness.

See docs/ai-platform-phase-6.md.
"""

from src.services.agents.workflow_observer.agent import (
    AGENT_WORKFLOW_OBSERVER,
    DetectorContext,
    MetaProposal,
    ScanResult,
    WorkflowObserverAgent,
)

__all__ = [
    "AGENT_WORKFLOW_OBSERVER",
    "DetectorContext",
    "MetaProposal",
    "ScanResult",
    "WorkflowObserverAgent",
]
