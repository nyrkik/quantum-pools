"""Tests for HandlerMismatchDetector — Phase 6 step 7.

Coverage:
- Below sample-size gate (<20): returns []
- Below abandonment threshold (<70%): returns []
- Above thresholds: produces a workflow_config proposal turning off the
  handler for that entity_type (`{entity_type: None}` merge)
- Multiple (entity_type, handler) pairs scored independently
- Events with missing payload/refs are ignored, not crashed
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from src.models.platform_event import PlatformEvent
from src.services.agents.workflow_observer.agent import DetectorContext
from src.services.agents.workflow_observer.detectors.handler_mismatch import (
    HandlerMismatchDetector,
    _confidence,
)


def _seed_event(
    db, *, org_id: str, event_type: str, handler: str, entity_type: str,
    when: datetime | None = None,
) -> None:
    db.add(PlatformEvent(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        event_type=event_type,
        actor_type="user",
        level="user_action",
        entity_refs={"entity_type": entity_type, "entity_id": str(uuid.uuid4())},
        payload={"handler": handler},
        created_at=when or datetime.now(timezone.utc),
    ))


def _ctx(org_id: str, db) -> DetectorContext:
    end = datetime.now(timezone.utc)
    return DetectorContext(
        org_id=org_id,
        window_start=end - timedelta(days=14),
        window_end=end,
        db=db,
    )


# ---------------------------------------------------------------------------
# Threshold gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_sample_size_returns_nothing(db_session, org_a):
    # 15 events total < 20 minimum
    for _ in range(12):
        _seed_event(db_session, org_id=org_a.id,
                    event_type="handler.abandoned",
                    handler="schedule_inline", entity_type="job")
    for _ in range(3):
        _seed_event(db_session, org_id=org_a.id,
                    event_type="handler.applied",
                    handler="schedule_inline", entity_type="job")
    await db_session.commit()

    out = await HandlerMismatchDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


@pytest.mark.asyncio
async def test_below_abandonment_returns_nothing(db_session, org_a):
    # 60% abandon rate, below 70% threshold
    for _ in range(12):
        _seed_event(db_session, org_id=org_a.id,
                    event_type="handler.abandoned",
                    handler="schedule_inline", entity_type="job")
    for _ in range(8):
        _seed_event(db_session, org_id=org_a.id,
                    event_type="handler.applied",
                    handler="schedule_inline", entity_type="job")
    await db_session.commit()

    out = await HandlerMismatchDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_abandonment_proposes_turnoff(db_session, org_a):
    # 18 abandons / 22 total = 0.818 abandonment rate
    for _ in range(18):
        _seed_event(db_session, org_id=org_a.id,
                    event_type="handler.abandoned",
                    handler="schedule_inline", entity_type="job")
    for _ in range(4):
        _seed_event(db_session, org_id=org_a.id,
                    event_type="handler.applied",
                    handler="schedule_inline", entity_type="job")
    await db_session.commit()

    out = await HandlerMismatchDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    p = out[0]
    assert p.detector_id == "handler_mismatch"
    assert p.entity_type == "workflow_config"
    assert p.payload["target"] == "post_creation_handlers"
    assert p.payload["op"] == "merge"
    assert p.payload["value"] == {"job": None}  # turn off
    assert p.evidence["abandoned_count"] == 18
    assert p.evidence["applied_count"] == 4
    assert p.evidence["total"] == 22
    assert "schedule_inline" in p.summary
    assert "18 of 22" in p.summary


@pytest.mark.asyncio
async def test_multiple_entity_types_scored_independently(db_session, org_a):
    # job: 18/22 abandoned (proposes), case: 5/22 abandoned (skipped)
    for _ in range(18):
        _seed_event(db_session, org_id=org_a.id, event_type="handler.abandoned",
                    handler="schedule_inline", entity_type="job")
    for _ in range(4):
        _seed_event(db_session, org_id=org_a.id, event_type="handler.applied",
                    handler="schedule_inline", entity_type="job")
    for _ in range(5):
        _seed_event(db_session, org_id=org_a.id, event_type="handler.abandoned",
                    handler="schedule_inline", entity_type="case")
    for _ in range(17):
        _seed_event(db_session, org_id=org_a.id, event_type="handler.applied",
                    handler="schedule_inline", entity_type="case")
    await db_session.commit()

    out = await HandlerMismatchDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    assert out[0].evidence["entity_type"] == "job"


@pytest.mark.asyncio
async def test_malformed_events_ignored_not_crashed(db_session, org_a):
    """Events missing handler in payload or entity_type in refs are
    dropped; healthy events still tally."""
    # 21 healthy abandons
    for _ in range(21):
        _seed_event(db_session, org_id=org_a.id, event_type="handler.abandoned",
                    handler="schedule_inline", entity_type="job")
    # 1 malformed (no handler in payload) — must not break
    db_session.add(PlatformEvent(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        event_type="handler.abandoned",
        actor_type="user",
        level="user_action",
        entity_refs={"entity_type": "job", "entity_id": str(uuid.uuid4())},
        payload={},  # missing handler
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    out = await HandlerMismatchDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    assert out[0].evidence["total"] == 21  # malformed dropped


# ---------------------------------------------------------------------------
# Confidence math
# ---------------------------------------------------------------------------


def test_confidence_below_sample_returns_zero():
    assert _confidence(1.0, 10) == 0.0


def test_confidence_at_min_sample_equals_rate():
    assert _confidence(0.85, 20) == pytest.approx(0.85)


def test_confidence_caps_at_99():
    assert _confidence(0.95, 200) == pytest.approx(0.99)
