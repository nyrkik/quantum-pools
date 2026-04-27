"""Detector registry for WorkflowObserverAgent.

v1 ships three detectors. Each implementation lives in its own module
in this package; the harness imports them from `DETECTORS` only — never
references individual detectors by name.

Steps 6/7/8 (DefaultAssignee, HandlerMismatch, ClassificationOverride)
will append to DETECTORS as each lands.
"""

from __future__ import annotations

from src.services.agents.workflow_observer.agent import Detector
from src.services.agents.workflow_observer.detectors.default_assignee import (
    DefaultAssigneeDetector,
)
from src.services.agents.workflow_observer.detectors.handler_mismatch import (
    HandlerMismatchDetector,
)


DETECTORS: list[Detector] = [
    DefaultAssigneeDetector(),
    HandlerMismatchDetector(),
]


__all__ = [
    "DETECTORS",
    "DefaultAssigneeDetector",
    "HandlerMismatchDetector",
]
