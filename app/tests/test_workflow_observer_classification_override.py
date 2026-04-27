"""Tests for ClassificationOverrideDetector — Phase 6 step 8.

Coverage:
- Below cluster size (<5): returns []
- Cluster of ≥5 same (from→to, sender_domain): produces an inbox_rule
  proposal with sender_domain condition + assign_category action
- Different (from, to) pairs scored independently
- Different sender domains scored independently
- Threads with no contact_email or non-email contact are dropped
- Confidence math: floor + per-override bonus
- End-to-end accept: the inbox_rule creator validates and inserts a
  real InboxRule on accept
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.agent_thread import AgentThread
from src.models.inbox_rule import InboxRule
from src.models.platform_event import PlatformEvent
from src.models.user import User
from src.services.agents.workflow_observer.agent import DetectorContext
from src.services.agents.workflow_observer.detectors.classification_override import (
    ClassificationOverrideDetector,
    _confidence,
    _extract_domain,
)
from src.services.events.platform_event_service import Actor
from src.services.proposals import ProposalService


def _seed_thread(db, org_id: str, contact_email: str) -> str:
    tid = str(uuid.uuid4())
    db.add(AgentThread(
        id=tid,
        organization_id=org_id,
        thread_key=f"test-{uuid.uuid4().hex[:8]}",
        contact_email=contact_email,
        subject="Test",
        status="pending",
        category="general",
        message_count=1,
        last_direction="inbound",
    ))
    return tid


def _seed_category_change(db, org_id: str, thread_id: str, from_cat: str, to_cat: str) -> None:
    db.add(PlatformEvent(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        event_type="thread.category_changed",
        actor_type="user",
        level="user_action",
        entity_refs={"thread_id": thread_id},
        payload={"from": from_cat, "to": to_cat},
        created_at=datetime.now(timezone.utc),
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
# Threshold gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_cluster_size_returns_nothing(db_session, org_a):
    for i in range(4):  # 4 < MIN_CLUSTER_SIZE=5
        tid = _seed_thread(db_session, org_a.id, f"u{i}@acme.com")
        _seed_category_change(db_session, org_a.id, tid, "general", "billing")
    await db_session.commit()

    out = await ClassificationOverrideDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cluster_produces_inbox_rule_proposal(db_session, org_a):
    for i in range(6):
        tid = _seed_thread(db_session, org_a.id, f"u{i}@acme.com")
        _seed_category_change(db_session, org_a.id, tid, "general", "billing")
    await db_session.commit()

    out = await ClassificationOverrideDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    p = out[0]
    assert p.detector_id == "classification_override"
    assert p.entity_type == "inbox_rule"
    assert p.payload["conditions"] == [{
        "field": "sender_domain",
        "operator": "equals",
        "value": "acme.com",
    }]
    assert p.payload["actions"] == [{
        "type": "assign_category",
        "params": {"category": "billing"},
    }]
    assert p.evidence["count"] == 6
    assert p.evidence["sender_domain"] == "acme.com"


@pytest.mark.asyncio
async def test_independent_pairs_independent_proposals(db_session, org_a):
    """Different (from, to) clusters surface separately."""
    for i in range(5):
        tid = _seed_thread(db_session, org_a.id, f"u{i}@acme.com")
        _seed_category_change(db_session, org_a.id, tid, "general", "billing")
    for i in range(6):
        tid = _seed_thread(db_session, org_a.id, f"x{i}@brick.com")
        _seed_category_change(db_session, org_a.id, tid, "general", "complaint")
    await db_session.commit()

    out = await ClassificationOverrideDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 2
    domains = {p.evidence["sender_domain"] for p in out}
    assert domains == {"acme.com", "brick.com"}


@pytest.mark.asyncio
async def test_threads_without_email_dropped(db_session, org_a):
    # 6 with valid emails (passes), 4 with non-email contact (dropped)
    for i in range(6):
        tid = _seed_thread(db_session, org_a.id, f"u{i}@acme.com")
        _seed_category_change(db_session, org_a.id, tid, "general", "billing")
    for i in range(4):
        tid = _seed_thread(db_session, org_a.id, f"phone-{i}")  # no @
        _seed_category_change(db_session, org_a.id, tid, "general", "billing")
    await db_session.commit()

    out = await ClassificationOverrideDetector().scan(_ctx(org_a.id, db_session))
    assert len(out) == 1
    assert out[0].evidence["count"] == 6


@pytest.mark.asyncio
async def test_no_op_changes_dropped(db_session, org_a):
    """Events where from == to (e.g. a redundant set) shouldn't count."""
    for i in range(7):
        tid = _seed_thread(db_session, org_a.id, f"u{i}@acme.com")
        _seed_category_change(db_session, org_a.id, tid, "billing", "billing")
    await db_session.commit()

    out = await ClassificationOverrideDetector().scan(_ctx(org_a.id, db_session))
    assert out == []


# ---------------------------------------------------------------------------
# Confidence math + helpers
# ---------------------------------------------------------------------------


def test_extract_domain():
    assert _extract_domain("user@acme.com") == "acme.com"
    assert _extract_domain("USER@Acme.COM") == "acme.com"
    assert _extract_domain("notanemail") is None
    assert _extract_domain("") is None


def test_confidence_below_floor():
    assert _confidence(4) == 0.0


def test_confidence_at_floor():
    assert _confidence(5) == pytest.approx(0.80)


def test_confidence_caps_at_99():
    assert _confidence(100) == pytest.approx(0.99)


# ---------------------------------------------------------------------------
# End-to-end: stage → accept → InboxRule row exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proposal_accepts_into_real_inbox_rule(db_session, org_a):
    user_id = str(uuid.uuid4())
    db_session.add(User(
        id=user_id,
        email=f"co-{uuid.uuid4().hex[:6]}@test.com",
        hashed_password="x", first_name="Class", last_name="Override",
    ))
    for i in range(5):
        tid = _seed_thread(db_session, org_a.id, f"u{i}@acme.com")
        _seed_category_change(db_session, org_a.id, tid, "general", "billing")
    await db_session.commit()

    metaproposals = await ClassificationOverrideDetector().scan(_ctx(org_a.id, db_session))
    assert len(metaproposals) == 1
    mp = metaproposals[0]

    # Stage via ProposalService (same path the harness would use).
    svc = ProposalService(db_session)
    p = await svc.stage(
        org_id=org_a.id,
        agent_type="workflow_observer",
        entity_type=mp.entity_type,
        source_type="organization",
        source_id=org_a.id,
        proposed_payload=mp.payload,
        confidence=mp.confidence,
        input_context=f"[{mp.detector_id}] {mp.summary}",
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, rule = await svc.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == "accepted"
    assert isinstance(rule, InboxRule)
    assert rule.organization_id == org_a.id
    assert rule.conditions[0]["field"] == "sender_domain"
    assert rule.conditions[0]["value"] == "acme.com"
    assert rule.actions[0]["type"] == "assign_category"
    assert rule.actions[0]["params"]["category"] == "billing"
