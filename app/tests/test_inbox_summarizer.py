"""Unit tests for InboxSummarizerService.

Exercise the shape/validation/parsing paths without calling the live
model. An integration-level test with a real Haiku call happens on
the deployed backend (too expensive + flaky to run in CI).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.services.agents.inbox_summarizer import (
    InboxSummarizerService,
    InboxSummary,
    _is_short_thread,
)


async def _seed_thread(db, org_id: str) -> str:
    t = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"sum-{uuid.uuid4().hex[:8]}",
        contact_email="customer@example.com",
        subject="Pool pump making noise",
        status="pending",
        category="service_request",
        message_count=0,
        last_direction="inbound",
    )
    db.add(t)
    await db.flush()
    return t.id


async def _seed_message(db, thread_id: str, org_id: str, body: str, direction: str = "inbound"):
    from datetime import datetime, timezone
    m = AgentMessage(
        id=str(uuid.uuid4()),
        thread_id=thread_id,
        organization_id=org_id,
        from_email="customer@example.com",
        to_email="inbox@quantumpoolspro.com",
        subject="x",
        body=body,
        direction=direction,
        received_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()


# -- Schema validation -----------------------------------------------------


def test_inbox_summary_validates_minimal_payload():
    s = InboxSummary.model_validate({
        "version": 1,
        "ask": "Can you come fix the pump?",
        "state": "Scheduled a repair visit for Thursday.",
        "open_items": [],
        "red_flags": [],
        "linked_refs": [],
        "confidence": 0.8,
    })
    assert s.ask == "Can you come fix the pump?"
    assert s.state.startswith("Scheduled")


def test_inbox_summary_state_whitespace_becomes_none():
    # Bullets are now the primary output; state is optional and only
    # populated when the thread has no discrete items. Whitespace-only
    # coerces to None rather than raising.
    s = InboxSummary.model_validate({
        "version": 1,
        "state": "   ",
        "confidence": 0.5,
    })
    assert s.state is None


def test_inbox_summary_state_can_be_null():
    s = InboxSummary.model_validate({
        "version": 1,
        "state": None,
        "open_items": ["Filter cleaning — Approved"],
        "confidence": 0.8,
    })
    assert s.state is None
    assert s.open_items == ["Filter cleaning — Approved"]


def test_inbox_summary_confidence_bounds():
    with pytest.raises(ValidationError):
        InboxSummary.model_validate({
            "version": 1, "confidence": 1.5,  # >1
        })
    with pytest.raises(ValidationError):
        InboxSummary.model_validate({
            "version": 1, "confidence": -0.1,
        })


# -- Short-thread heuristic ------------------------------------------------


class _FakeMsg:
    """Duck-typed stand-in — _is_short_thread only reads .body."""
    def __init__(self, body: str):
        self.body = body


def test_is_short_thread_true_for_single_msg():
    assert _is_short_thread([_FakeMsg("Thanks!")]) is True


def test_is_short_thread_false_for_meaty_thread():
    msgs = [_FakeMsg("x" * 1000) for _ in range(3)]
    assert _is_short_thread(msgs) is False


# -- Output parsing --------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_handles_fenced_json(db_session):
    svc = InboxSummarizerService(db_session)
    raw = """```json
    {
      "version": 1,
      "ask": "When is the next service?",
      "state": "Next scheduled Tuesday.",
      "open_items": ["confirm time with client"],
      "red_flags": [],
      "linked_refs": [],
      "confidence": 0.9,
      "proposals": []
    }
    ```"""
    s = svc._parse_and_validate(raw)
    assert s.state == "Next scheduled Tuesday."
    assert s.confidence == 0.9


@pytest.mark.asyncio
async def test_parse_strips_proposals_key_from_summary_validation(db_session):
    """Summary schema doesn't include `proposals` — service extracts
    them separately via _extract_proposals."""
    svc = InboxSummarizerService(db_session)
    raw = json.dumps({
        "version": 1, "ask": "x", "state": "y", "confidence": 0.7,
        "proposals": [{"entity_type": "job", "payload": {"action_type": "repair", "description": "Fix pump"}}],
    })
    s = svc._parse_and_validate(raw)
    # Survived without a proposals field (would fail if not stripped)
    assert s.state == "y"

    drafts = svc._extract_proposals(raw)
    assert len(drafts) == 1
    assert drafts[0].entity_type == "job"


@pytest.mark.asyncio
async def test_parse_raises_on_missing_json(db_session):
    svc = InboxSummarizerService(db_session)
    with pytest.raises(ValueError):
        svc._parse_and_validate("I am a chatty model with no JSON output at all")


# -- End-to-end-ish path with mocked model ---------------------------------


@pytest.mark.asyncio
async def test_summarize_short_thread_skips_and_emits(
    db_session, org_a, event_recorder,
):
    """Short thread: no summary cached, thread.summarized fires with
    skipped_reason='short_thread'."""
    tid = await _seed_thread(db_session, org_a.id)
    await _seed_message(db_session, tid, org_a.id, "Thanks!")
    await db_session.commit()

    svc = InboxSummarizerService(db_session)
    result = await svc.summarize_thread(tid)
    await db_session.commit()

    assert result is None
    thread = await db_session.get(AgentThread, tid)
    assert thread.ai_summary_payload is None
    assert thread.ai_summary_generated_at is not None  # short-circuit was marked done

    event = await event_recorder.assert_emitted("thread.summarized", thread_id=tid)
    assert event["payload"]["skipped_reason"] == "short_thread"


@pytest.mark.asyncio
async def test_summarize_caches_and_fires_event(
    db_session, org_a, event_recorder,
):
    """Meaty thread with a mocked model response → payload cached +
    thread.summarized emitted with confidence."""
    tid = await _seed_thread(db_session, org_a.id)
    for _ in range(3):
        await _seed_message(db_session, tid, org_a.id, "x" * 300)
    await db_session.commit()

    fake_response = json.dumps({
        "version": 1,
        "ask": "Can you check the filter?",
        "state": "Need to schedule site visit this week.",
        "open_items": ["call back to confirm time"],
        "red_flags": [],
        "linked_refs": [],
        "confidence": 0.85,
        "proposals": [],
    })

    with patch.object(
        InboxSummarizerService, "_call_model",
        return_value=fake_response,
    ):
        svc = InboxSummarizerService(db_session)
        summary = await svc.summarize_thread(tid)
        await db_session.commit()

    assert summary is not None
    assert summary.confidence == 0.85
    thread = await db_session.get(AgentThread, tid)
    assert thread.ai_summary_payload is not None
    assert thread.ai_summary_payload["state"] == "Need to schedule site visit this week."
    assert thread.ai_summary_version == 1

    await event_recorder.assert_emitted("thread.summarized", thread_id=tid)


@pytest.mark.asyncio
async def test_summarize_low_confidence_does_not_cache(
    db_session, org_a, event_recorder,
):
    tid = await _seed_thread(db_session, org_a.id)
    for _ in range(3):
        await _seed_message(db_session, tid, org_a.id, "x" * 300)
    await db_session.commit()

    fake_response = json.dumps({
        "version": 1,
        "ask": "vague",
        "state": "unclear.",
        "open_items": [],
        "red_flags": [],
        "linked_refs": [],
        "confidence": 0.2,  # below floor
        "proposals": [],
    })

    with patch.object(
        InboxSummarizerService, "_call_model",
        return_value=fake_response,
    ):
        svc = InboxSummarizerService(db_session)
        result = await svc.summarize_thread(tid)
        await db_session.commit()

    assert result is None
    thread = await db_session.get(AgentThread, tid)
    assert thread.ai_summary_payload is None  # not cached

    event = await event_recorder.assert_emitted("thread.summarized", thread_id=tid)
    assert event["payload"]["skipped_reason"] == "low_confidence"


@pytest.mark.asyncio
async def test_summarize_model_error_leaves_cache_intact(
    db_session, org_a, event_recorder,
):
    """If the model call raises, agent.error fires + thread.summarized
    does NOT fire, and any prior cache is left alone."""
    tid = await _seed_thread(db_session, org_a.id)
    for _ in range(3):
        await _seed_message(db_session, tid, org_a.id, "x" * 300)
    # Pre-populate a stale cache to verify it's not clobbered.
    thread = await db_session.get(AgentThread, tid)
    thread.ai_summary_payload = {"state": "prior summary", "confidence": 0.9}
    thread.ai_summary_version = 1
    await db_session.commit()

    async def boom(self, prompt):
        raise RuntimeError("network flake")

    with patch.object(InboxSummarizerService, "_call_model", new=boom):
        svc = InboxSummarizerService(db_session)
        result = await svc.summarize_thread(tid)
        await db_session.commit()

    assert result is None
    thread = await db_session.get(AgentThread, tid)
    assert thread.ai_summary_payload == {"state": "prior summary", "confidence": 0.9}

    await event_recorder.assert_emitted("agent.error", thread_id=tid)


@pytest.mark.asyncio
async def test_summarize_stages_proposals(
    db_session, org_a, event_recorder,
):
    tid = await _seed_thread(db_session, org_a.id)
    for _ in range(3):
        await _seed_message(db_session, tid, org_a.id, "x" * 300)
    await db_session.commit()

    fake_response = json.dumps({
        "version": 1,
        "ask": "Can you replace the filter cartridge?",
        "state": "Need to schedule replacement + order part.",
        "open_items": [],
        "red_flags": [],
        "linked_refs": [],
        "confidence": 0.88,
        "proposals": [
            {"entity_type": "job", "payload": {
                "action_type": "repair",
                "description": "Replace filter cartridge — pending order",
            }},
        ],
    })

    with patch.object(InboxSummarizerService, "_call_model", return_value=fake_response):
        svc = InboxSummarizerService(db_session)
        summary = await svc.summarize_thread(tid)
        await db_session.commit()

    assert summary is not None
    assert len(summary.proposal_ids) == 1
    # The staged proposal exists in agent_proposals
    from src.models.agent_proposal import AgentProposal
    p = await db_session.get(AgentProposal, summary.proposal_ids[0])
    assert p is not None
    assert p.agent_type == "inbox_summarizer"
    assert p.entity_type == "job"
    assert p.source_type == "agent_thread"
    assert p.source_id == tid

    # Both events fired
    await event_recorder.assert_emitted("proposal.staged", agent_proposal_id=p.id)
    event = await event_recorder.assert_emitted("thread.summarized", thread_id=tid)
    assert event["payload"]["proposals_staged"] == 1
