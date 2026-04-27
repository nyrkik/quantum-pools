"""Detector registry for WorkflowObserverAgent.

v1 ships three detectors. Each implementation lives in its own module
once we start adding logic; the empty list here lets step 5 ship with a
working harness that we can verify end-to-end before any pattern code
runs.

Steps 6/7/8 (DefaultAssignee, HandlerMismatch, ClassificationOverride)
will append to DETECTORS as each lands.
"""

from __future__ import annotations

from src.services.agents.workflow_observer.agent import Detector


DETECTORS: list[Detector] = []
