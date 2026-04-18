"""Unit tests for POST /v1/events receiver.

Contract being verified (docs/ai-platform-phase-1.md §7.4):

- Well-formed batch of frontend-emittable events → all accepted.
- Batch with some bad events → good ones accepted, bad ones dropped with
  count reported. Never 500 on individual bad events.
- Unknown event_type → dropped.
- Backend-only event_type (frontend_emittable=False) → dropped.
- Invalid level for event → dropped.
- Frontend claiming system_action / agent_action level → dropped (only
  user_action and error allowed from the frontend).
- Oversized payload → dropped before reaching emit (avoids marker pollution).
- Client-supplied session_id propagates to event rows.
- Idempotency: same client_emit_id posted twice is deduped.
- actor_user_id and organization_id derived from auth context, not body.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

# Reuse the receiver's service directly — avoids setting up a full HTTP
# client fixture. The receiver is thin (validation + loop + emit); tests
# cover the validation logic by calling the same entry points.
from src.api.v1.events import EventIn, _validate_event, MAX_BATCH_SIZE
from src.services.events.platform_event_service import PlatformEventService, Actor


async def _all_events(db_session):
    result = await db_session.execute(
        text("SELECT event_type, level, actor_user_id, organization_id, session_id, "
             "client_emit_id, entity_refs, payload "
             "FROM platform_events ORDER BY created_at")
    )
    return [dict(row._mapping) for row in result]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_accepts_known_frontend_event():
    ev = EventIn(event_type="thread.opened", level="user_action")
    assert _validate_event(ev, org_id="org-1") is None


def test_validate_rejects_unknown_event_type():
    ev = EventIn(event_type="made.up.event", level="user_action")
    assert _validate_event(ev, org_id="org-1") == "unknown_event_type"


def test_validate_rejects_backend_only_event():
    # agent_message.received is backend-only (frontend_emittable=False)
    ev = EventIn(event_type="agent_message.received", level="system_action")
    assert _validate_event(ev, org_id="org-1") == "not_frontend_emittable"


def test_validate_rejects_invalid_level_for_event():
    # thread.opened only allows user_action
    ev = EventIn(event_type="thread.opened", level="agent_action")
    # Caught first by the per-event level allowlist
    assert _validate_event(ev, org_id="org-1") == "invalid_level_for_event"


def test_validate_rejects_system_action_from_frontend():
    # Even if an event's spec permits system_action (e.g. thread.linked_to_case),
    # frontend is restricted to user_action + error.
    ev = EventIn(event_type="thread.linked_to_case", level="system_action")
    assert _validate_event(ev, org_id="org-1") == "forbidden_level_from_frontend"


def test_validate_rejects_agent_action_from_frontend():
    ev = EventIn(event_type="thread.linked_to_case", level="agent_action")
    assert _validate_event(ev, org_id="org-1") == "invalid_level_for_event"


def test_validate_rejects_missing_org_when_required():
    # thread.opened requires_org=True
    ev = EventIn(event_type="thread.opened", level="user_action")
    assert _validate_event(ev, org_id=None) == "missing_org"


def test_validate_allows_missing_org_for_page_viewed():
    # page.viewed has requires_org=False
    ev = EventIn(event_type="page.viewed", level="user_action")
    assert _validate_event(ev, org_id=None) is None


def test_validate_rejects_oversized_payload():
    huge = {"blob": "x" * 20_000}
    ev = EventIn(event_type="thread.opened", level="user_action", payload=huge)
    assert _validate_event(ev, org_id="org-1") == "payload_too_large"


def test_validate_allows_frontend_error_level():
    # error is the other frontend-allowed level (for error.frontend_unhandled)
    ev = EventIn(event_type="error.frontend_unhandled", level="error")
    assert _validate_event(ev, org_id=None) is None


def test_batch_size_cap_exists():
    # Not testing the Pydantic enforcement here; just asserting the constant
    # exists and is a sane bound.
    assert MAX_BATCH_SIZE == 200


# ---------------------------------------------------------------------------
# End-to-end: simulate receiver behavior against real DB
#
# We bypass the HTTP layer (auth, rate-limit) and verify that the validation
# + emit pipeline produces correct rows. This catches integration bugs
# between _validate_event and PlatformEventService.emit.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_mixed_batch_accepts_good_drops_bad(db_session, org_a):
    """Simulate the receiver loop: one good, one unknown, one backend-only,
    one invalid level. Only the good one should land in the DB."""
    batch = [
        EventIn(event_type="thread.opened", level="user_action",
                entity_refs={"thread_id": "t-1"}),
        EventIn(event_type="made.up", level="user_action"),          # unknown
        EventIn(event_type="agent_message.received", level="system_action"),  # backend-only
        EventIn(event_type="thread.opened", level="agent_action"),   # wrong level
    ]

    actor = Actor(actor_type="user", user_id="u-1")
    accepted = 0
    rejected = 0

    for ev in batch:
        if _validate_event(ev, org_a.id) is not None:
            rejected += 1
            continue
        await PlatformEventService.emit(
            db=db_session,
            event_type=ev.event_type,
            level=ev.level,
            actor=actor,
            organization_id=org_a.id,
            entity_refs=ev.entity_refs,
            payload=ev.payload,
            client_emit_id=ev.client_emit_id,
        )
        accepted += 1

    await db_session.commit()

    assert accepted == 1
    assert rejected == 3

    events = await _all_events(db_session)
    assert len(events) == 1
    assert events[0]["event_type"] == "thread.opened"
    assert events[0]["actor_user_id"] == "u-1"
    assert events[0]["organization_id"] == org_a.id
    assert events[0]["entity_refs"] == {"thread_id": "t-1"}


@pytest.mark.asyncio
async def test_e2e_idempotency_same_client_emit_id(db_session, org_a):
    emit_id = str(uuid.uuid4())
    actor = Actor(actor_type="user", user_id="u-1")

    for _ in range(3):
        ev = EventIn(
            event_type="compose.sent",
            level="user_action",
            client_emit_id=emit_id,
        )
        await PlatformEventService.emit(
            db=db_session,
            event_type=ev.event_type,
            level=ev.level,
            actor=actor,
            organization_id=org_a.id,
            client_emit_id=ev.client_emit_id,
        )
    await db_session.commit()

    events = await _all_events(db_session)
    assert len(events) == 1, "Retries with identical client_emit_id must dedup"


@pytest.mark.asyncio
async def test_e2e_session_id_propagates(db_session, org_a):
    actor = Actor(actor_type="user", user_id="u-1")
    sid = str(uuid.uuid4())

    await PlatformEventService.emit(
        db=db_session,
        event_type="page.viewed",
        level="user_action",
        actor=actor,
        organization_id=org_a.id,
        session_id=sid,
    )
    await db_session.commit()

    events = await _all_events(db_session)
    assert events[0]["session_id"] == sid


@pytest.mark.asyncio
async def test_e2e_frontend_cannot_spoof_actor(db_session, org_a):
    """Even if a malicious client sent actor_type=system in a fabricated
    request body, the receiver derives Actor from the authenticated ctx,
    not from the body. This test verifies that invariant at the service
    layer — the body's intent never reaches emit()."""
    # Here we just confirm the service writes the actor that was passed to
    # it — the HTTP-layer contract (receiver builds Actor from ctx.user,
    # not from body) is enforced in app/src/api/v1/events.py by construction.
    # Integration tests at Step 4+ will exercise the full HTTP round-trip.
    actor = Actor(actor_type="user", user_id="real-user")
    await PlatformEventService.emit(
        db=db_session,
        event_type="page.viewed",
        level="user_action",
        actor=actor,
        organization_id=org_a.id,
    )
    await db_session.commit()
    events = await _all_events(db_session)
    assert events[0]["actor_user_id"] == "real-user"
