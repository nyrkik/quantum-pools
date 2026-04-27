"""Tests for DefaultAssigneeDetector — Phase 6 step 6.

Coverage:
- Below sample-size gate (<10): returns []
- Below dominance threshold (<80%): returns []
- Above thresholds with first_name assignments: resolves to user_id and
  produces a `fixed` strategy proposal
- Above thresholds with UUID-shaped assignee values: passes through
  without lookup
- Unresolvable first_name (no matching org user): silently skipped
- Confidence calculation respects sample size
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models.agent_action import AgentAction
from src.models.organization_user import OrganizationUser, OrgRole
from src.models.user import User
from src.services.agents.workflow_observer.agent import DetectorContext
from src.services.agents.workflow_observer.detectors.default_assignee import (
    DefaultAssigneeDetector,
    _confidence,
)


async def _seed_user_in_org(db, org_id: str, first_name: str = "Brian") -> str:
    user_id = str(uuid.uuid4())
    db.add(User(
        id=user_id,
        email=f"{first_name.lower()}-{uuid.uuid4().hex[:6]}@test.com",
        hashed_password="x",
        first_name=first_name,
        last_name="Tester",
        is_active=True,
    ))
    db.add(OrganizationUser(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org_id,
        role=OrgRole.owner,
    ))
    await db.flush()
    return user_id


def _seed_action(db, org_id: str, assigned_to: str | None = "Brian") -> None:
    db.add(AgentAction(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        action_type="job",
        description=f"Test action {uuid.uuid4().hex[:6]}",
        status="open",
        assigned_to=assigned_to,
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
    await _seed_user_in_org(db_session, org_a.id)
    for _ in range(9):  # 9 < MIN_SAMPLE_SIZE=10
        _seed_action(db_session, org_a.id, assigned_to="Brian")
    await db_session.commit()

    out = await DefaultAssigneeDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


@pytest.mark.asyncio
async def test_below_dominance_returns_nothing(db_session, org_a):
    """8/10 = 0.80 — at the boundary. Use 7/10 to be clearly below."""
    await _seed_user_in_org(db_session, org_a.id, "Brian")
    await _seed_user_in_org(db_session, org_a.id, "Sarah")
    for _ in range(7):
        _seed_action(db_session, org_a.id, assigned_to="Brian")
    for _ in range(3):
        _seed_action(db_session, org_a.id, assigned_to="Sarah")
    await db_session.commit()

    out = await DefaultAssigneeDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_name_resolves_to_user_id(db_session, org_a):
    user_id = await _seed_user_in_org(db_session, org_a.id, "Brian")
    for _ in range(12):
        _seed_action(db_session, org_a.id, assigned_to="Brian")
    await db_session.commit()

    out = await DefaultAssigneeDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    proposal = out[0]
    assert proposal.detector_id == "default_assignee"
    assert proposal.entity_type == "workflow_config"
    assert proposal.payload["target"] == "default_assignee_strategy"
    assert proposal.payload["op"] == "set"
    assert proposal.payload["value"] == {
        "strategy": "fixed",
        "fallback_user_id": user_id,
    }
    assert "12 of 12 jobs" in proposal.summary
    assert proposal.evidence["sample_size"] == 12
    assert proposal.evidence["dominant_count"] == 12
    assert proposal.evidence["ratio"] == 1.0


@pytest.mark.asyncio
async def test_uuid_value_passes_through(db_session, org_a):
    """When assigned_to already contains a user_id, the detector skips
    the first_name lookup and uses it directly."""
    user_id = await _seed_user_in_org(db_session, org_a.id, "Brian")
    for _ in range(11):
        _seed_action(db_session, org_a.id, assigned_to=user_id)
    await db_session.commit()

    out = await DefaultAssigneeDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    assert out[0].payload["value"]["fallback_user_id"] == user_id


@pytest.mark.asyncio
async def test_unresolvable_name_silently_skipped(db_session, org_a):
    """A first_name with no matching org user produces no proposal —
    surfacing an unresolvable suggestion would just confuse the admin."""
    # Note: NO user seeded with first_name="Ghost".
    for _ in range(15):
        _seed_action(db_session, org_a.id, assigned_to="Ghost")
    await db_session.commit()

    out = await DefaultAssigneeDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


# ---------------------------------------------------------------------------
# Confidence math
# ---------------------------------------------------------------------------


def test_confidence_below_min_sample_returns_zero():
    assert _confidence(1.0, 5) == 0.0


def test_confidence_at_min_sample_equals_ratio():
    assert _confidence(0.85, 10) == pytest.approx(0.85)


def test_confidence_sample_size_bonus_applies():
    # ratio=0.80, N=20: bonus = 0.005 * 10 = 0.05 → 0.85
    assert _confidence(0.80, 20) == pytest.approx(0.85)
    # ratio=0.80, N=50: 0.80 + 0.005 * 40 = 1.00, capped at 0.99
    assert _confidence(0.80, 50) == pytest.approx(0.99)
    # ratio=0.95, N=100: also capped
    assert _confidence(0.95, 100) == pytest.approx(0.99)
