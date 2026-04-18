"""Integration-test helper for asserting emitted events.

Design reference: docs/ai-platform-phase-1.md §11.2.

Usage:

    async def test_inbox_flow(db_session, event_recorder, ...):
        # ... exercise business logic ...
        await event_recorder.assert_emitted("thread.archived", thread_id="abc")
        events = await event_recorder.all_of_type("agent_message.classified")
        assert len(events) == 1

The recorder queries `platform_events` — it doesn't mock or intercept emit.
This means tests verify the actual DB row shape, not a mocked call graph.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EventRecorder:
    """Query and assert against rows in `platform_events` for a single test."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def all(self) -> list[dict[str, Any]]:
        """Return every event in the test DB, ordered by created_at."""
        result = await self._db.execute(
            text(
                "SELECT id, organization_id, actor_user_id, actor_type, "
                "actor_agent_type, event_type, level, entity_refs, payload, "
                "request_id, session_id, job_run_id, client_emit_id, created_at "
                "FROM platform_events ORDER BY created_at ASC"
            )
        )
        return [dict(row._mapping) for row in result]

    async def all_of_type(self, event_type: str) -> list[dict[str, Any]]:
        result = await self._db.execute(
            text(
                "SELECT id, organization_id, actor_user_id, actor_type, "
                "actor_agent_type, event_type, level, entity_refs, payload, "
                "created_at "
                "FROM platform_events WHERE event_type = :etype "
                "ORDER BY created_at ASC"
            ),
            {"etype": event_type},
        )
        return [dict(row._mapping) for row in result]

    async def find(self, event_type: str, **entity_ref_filters: str) -> Optional[dict[str, Any]]:
        """First event of this type matching the entity_refs filter, or None."""
        matches = await self._matching(event_type, entity_ref_filters)
        return matches[0] if matches else None

    async def assert_emitted(self, event_type: str, **entity_ref_filters: str) -> dict[str, Any]:
        """Assert at least one event of this type + entity_refs was emitted.

        Returns the first match so the caller can do further field-level
        assertions on payload, actor, etc.
        """
        matches = await self._matching(event_type, entity_ref_filters)
        if not matches:
            all_events = await self.all()
            summary = sorted({e["event_type"] for e in all_events})
            raise AssertionError(
                f"No {event_type!r} event found with refs {entity_ref_filters}. "
                f"Events in DB: {summary}"
            )
        return matches[0]

    async def assert_not_emitted(self, event_type: str, **entity_ref_filters: str) -> None:
        matches = await self._matching(event_type, entity_ref_filters)
        if matches:
            raise AssertionError(
                f"Expected no {event_type!r} events with refs {entity_ref_filters}, "
                f"found {len(matches)}."
            )

    async def count(self) -> int:
        result = await self._db.execute(text("SELECT COUNT(*) FROM platform_events"))
        return int(result.scalar() or 0)

    async def _matching(
        self, event_type: str, entity_ref_filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        events = await self.all_of_type(event_type)
        if not entity_ref_filters:
            return events
        return [
            e
            for e in events
            if all(
                e.get("entity_refs", {}).get(k) == v
                for k, v in entity_ref_filters.items()
            )
        ]


@pytest_asyncio.fixture
async def event_recorder(db_session) -> EventRecorder:
    """Fixture: fresh recorder per test. Relies on conftest's TRUNCATE-between
    -tests isolation (no events from prior tests leak into queries)."""
    return EventRecorder(db_session)
