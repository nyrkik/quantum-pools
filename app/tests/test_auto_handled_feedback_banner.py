"""Auto-handled feedback banner must not reappear after ack.

Regression guard — the Bill Hoge / insurance-folder case where the
user clicked Yes twice and the banner kept coming back. Root cause
was that ack state was React-local only; the backend only updated
the thread when the user said No. Fixed by persisting an
``auto_handled_feedback_at`` timestamp on every Yes/No + honoring
it in the presenter's ``is_auto_handled`` derivation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models.agent_thread import AgentThread
from src.presenters.thread_presenter import ThreadPresenter


async def _seed_auto_handled_thread(db, org_id: str) -> AgentThread:
    t = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"auto-handled|{uuid.uuid4().hex[:8]}",
        contact_email="bill@example.com",
        subject="Insurance docs",
        last_direction="inbound",
        status="handled",
        has_pending=False,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()
    return t


@pytest.mark.asyncio
async def test_is_auto_handled_true_when_not_yet_acknowledged(db_session, org_a):
    t = await _seed_auto_handled_thread(db_session, org_a.id)
    d = await ThreadPresenter(db_session).one(t)
    assert d["is_auto_handled"] is True


@pytest.mark.asyncio
async def test_is_auto_handled_false_after_ack(db_session, org_a):
    """Yes + No both stamp ``auto_handled_feedback_at``; presenter
    must treat the thread as no-longer-auto-handled after that, so
    the banner stops rendering on future opens."""
    t = await _seed_auto_handled_thread(db_session, org_a.id)
    t.auto_handled_feedback_at = datetime.now(timezone.utc)
    await db_session.flush()
    d = await ThreadPresenter(db_session).one(t)
    assert d["is_auto_handled"] is False
