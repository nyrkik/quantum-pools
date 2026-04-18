"""Unit tests for PlatformEventService.emit().

Contract being verified (docs/ai-platform-phase-1.md §5.1,
docs/event-taxonomy.md):

- Basic happy path: row inserted with all required fields.
- Idempotency: second emit with same client_emit_id is a no-op.
- Oversized payload: truncated to marker + separate oversized event logged.
- Fail-soft: DB errors don't propagate to the caller.
- Context propagation: request_id / session_id / job_run_id pulled from
  contextvars when not supplied explicitly.
- Actor fields: user / system / agent all round-trip correctly.
"""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.services.events.platform_event_service import (
    PlatformEventService,
    Actor,
    actor_system,
    actor_agent,
    set_request_id,
    reset_request_id,
    set_session_id,
    reset_session_id,
)
from src.services.events.job_run_context import job_run_context


async def _all_events(db_session):
    """Load all events from the test DB as list of dicts."""
    result = await db_session.execute(
        text("SELECT * FROM platform_events ORDER BY created_at ASC")
    )
    return [dict(row._mapping) for row in result]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_writes_a_row(db_session, org_a):
    await PlatformEventService.emit(
        db=db_session,
        event_type="test.basic",
        level="user_action",
        actor=Actor(actor_type="user", user_id="u-1"),
        organization_id=org_a.id,
        entity_refs={"customer_id": "c-1"},
        payload={"note": "hello"},
    )
    await db_session.commit()

    events = await _all_events(db_session)
    assert len(events) == 1
    e = events[0]
    assert e["event_type"] == "test.basic"
    assert e["level"] == "user_action"
    assert e["actor_type"] == "user"
    assert e["actor_user_id"] == "u-1"
    assert e["organization_id"] == org_a.id
    assert e["entity_refs"] == {"customer_id": "c-1"}
    assert e["payload"] == {"note": "hello"}


@pytest.mark.asyncio
async def test_emit_system_actor_has_no_user(db_session, org_a):
    await PlatformEventService.emit(
        db=db_session,
        event_type="system.sweep.ran",
        level="system_action",
        actor=actor_system(),
        organization_id=org_a.id,
    )
    await db_session.commit()

    events = await _all_events(db_session)
    assert events[0]["actor_type"] == "system"
    assert events[0]["actor_user_id"] is None


@pytest.mark.asyncio
async def test_emit_agent_actor_carries_agent_type(db_session, org_a):
    await PlatformEventService.emit(
        db=db_session,
        event_type="agent.generated",
        level="agent_action",
        actor=actor_agent("email_drafter"),
        organization_id=org_a.id,
    )
    await db_session.commit()

    events = await _all_events(db_session)
    assert events[0]["actor_type"] == "agent"
    assert events[0]["actor_agent_type"] == "email_drafter"


@pytest.mark.asyncio
async def test_emit_accepts_null_org_for_platform_events(db_session):
    # Pre-auth events like login_failed have null organization_id
    await PlatformEventService.emit(
        db=db_session,
        event_type="user.login_failed",
        level="error",
        actor=actor_system(),
        organization_id=None,
        payload={"reason": "bad_password"},
    )
    await db_session.commit()
    events = await _all_events(db_session)
    assert events[0]["organization_id"] is None


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_same_client_emit_id_is_deduped(db_session, org_a):
    emit_id = str(uuid.uuid4())
    for _ in range(3):
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.idempotent",
            level="user_action",
            actor=Actor(),
            organization_id=org_a.id,
            client_emit_id=emit_id,
        )
    await db_session.commit()

    events = await _all_events(db_session)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_emit_different_client_emit_ids_all_insert(db_session, org_a):
    for _ in range(3):
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.not_dedup",
            level="user_action",
            actor=Actor(),
            organization_id=org_a.id,
            client_emit_id=str(uuid.uuid4()),
        )
    await db_session.commit()
    events = await _all_events(db_session)
    assert len(events) == 3


@pytest.mark.asyncio
async def test_emit_no_client_emit_id_never_dedups(db_session, org_a):
    # When client_emit_id is None, idempotency doesn't apply — each call inserts.
    for _ in range(3):
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.no_dedup",
            level="user_action",
            actor=Actor(),
            organization_id=org_a.id,
        )
    await db_session.commit()
    events = await _all_events(db_session)
    assert len(events) == 3


# ---------------------------------------------------------------------------
# Oversized payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_oversized_payload_is_truncated(db_session, org_a):
    huge_payload = {"blob": "x" * 20_000}  # well over 8KB
    await PlatformEventService.emit(
        db=db_session,
        event_type="test.oversized",
        level="user_action",
        actor=Actor(),
        organization_id=org_a.id,
        payload=huge_payload,
    )
    await db_session.commit()

    events = await _all_events(db_session)
    # Two events: the caller's (with truncated payload) and the oversized-marker error event
    types = sorted(e["event_type"] for e in events)
    assert "test.oversized" in types
    assert "platform_event.oversized_payload" in types

    # The original event's payload should be replaced with the marker shape
    original = next(e for e in events if e["event_type"] == "test.oversized")
    assert original["payload"].get("__oversized__") is True
    assert original["payload"].get("original_size_bytes", 0) > 8 * 1024

    # The oversized-payload event is level=error
    marker = next(e for e in events if e["event_type"] == "platform_event.oversized_payload")
    assert marker["level"] == "error"


# ---------------------------------------------------------------------------
# Fail-soft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_never_raises_on_bad_sql(db_session, org_a, monkeypatch):
    # Force the insert SQL to fail by passing an invalid enum value.
    # The service wraps everything in try/except — no exception should escape.
    await PlatformEventService.emit(
        db=db_session,
        event_type="test.fail_soft",
        level="not_a_valid_level",  # violates CHECK constraint
        actor=Actor(),
        organization_id=org_a.id,
    )
    # No rollback issued by emit itself. Caller's session has a failed txn,
    # but the function returned normally.
    # To not leave the test's db_session in a broken state for further
    # operations, rollback here manually.
    await db_session.rollback()
    # If we got here, emit() didn't raise.


@pytest.mark.asyncio
async def test_emit_never_raises_on_non_serializable_payload(db_session, org_a):
    class NotSerializable:
        pass

    # json.dumps inside emit() would raise TypeError on this — but emit
    # swallows it.
    await PlatformEventService.emit(
        db=db_session,
        event_type="test.bad_payload",
        level="user_action",
        actor=Actor(),
        organization_id=org_a.id,
        payload={"bad": NotSerializable()},  # type: ignore[dict-item]
    )
    await db_session.rollback()


# ---------------------------------------------------------------------------
# Context propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_reads_request_id_from_contextvar(db_session, org_a):
    rid = str(uuid.uuid4())
    token = set_request_id(rid)
    try:
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.request_ctx",
            level="user_action",
            actor=Actor(),
            organization_id=org_a.id,
        )
        await db_session.commit()
    finally:
        reset_request_id(token)

    events = await _all_events(db_session)
    assert events[0]["request_id"] == rid


@pytest.mark.asyncio
async def test_emit_reads_session_id_from_contextvar(db_session, org_a):
    sid = str(uuid.uuid4())
    token = set_session_id(sid)
    try:
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.session_ctx",
            level="user_action",
            actor=Actor(),
            organization_id=org_a.id,
        )
        await db_session.commit()
    finally:
        reset_session_id(token)

    events = await _all_events(db_session)
    assert events[0]["session_id"] == sid


@pytest.mark.asyncio
async def test_emit_inherits_job_run_id_from_context_manager(db_session, org_a):
    async with job_run_context("retention_purge") as jid:
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.job_ctx",
            level="system_action",
            actor=actor_system(),
            organization_id=org_a.id,
        )
        await db_session.commit()

    events = await _all_events(db_session)
    assert events[0]["job_run_id"] == jid


@pytest.mark.asyncio
async def test_emit_explicit_value_overrides_contextvar(db_session, org_a):
    token = set_request_id("ctx-rid")
    try:
        explicit = "explicit-rid"
        await PlatformEventService.emit(
            db=db_session,
            event_type="test.explicit_override",
            level="user_action",
            actor=Actor(),
            organization_id=org_a.id,
            request_id=explicit,
        )
        await db_session.commit()
    finally:
        reset_request_id(token)

    events = await _all_events(db_session)
    assert events[0]["request_id"] == "explicit-rid"


# ---------------------------------------------------------------------------
# Actor details (acting_as + view_as_role)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_impersonation_fields_round_trip(db_session, org_a):
    await PlatformEventService.emit(
        db=db_session,
        event_type="test.impersonation",
        level="user_action",
        actor=Actor(
            actor_type="user",
            user_id="real-user",
            acting_as_user_id="target-user",
            view_as_role="technician",
        ),
        organization_id=org_a.id,
    )
    await db_session.commit()

    events = await _all_events(db_session)
    e = events[0]
    assert e["actor_user_id"] == "real-user"
    assert e["acting_as_user_id"] == "target-user"
    assert e["view_as_role"] == "technician"
