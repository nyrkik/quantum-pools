"""Tests for scripts/port_draft_response_to_proposals.py.

Seeds each message-status scenario the port handles, runs the port, asserts
status mapping + correction_type derivation + idempotency. Fixture DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from scripts.port_draft_response_to_proposals import port
from src.models.agent_correction import AgentCorrection
from src.models.agent_message import AgentMessage
from src.models.agent_proposal import (
    STATUS_ACCEPTED,
    STATUS_EDITED,
    STATUS_REJECTED,
    STATUS_STAGED,
    AgentProposal,
)
from src.models.agent_thread import AgentThread
from sqlalchemy import select


async def _mk_thread(db, org_id):
    t = AgentThread(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        thread_key=f"port-test|{uuid.uuid4().hex[:6]}",
        status="handled",
        contact_email="sender@example.com",
        subject="test",
    )
    db.add(t)
    await db.flush()
    return t


async def _mk_msg(db, org_id, thread_id, *, status: str, draft: str, final: str | None = None,
                  received_at: datetime | None = None) -> AgentMessage:
    received_at = received_at or datetime.now(timezone.utc)
    m = AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        direction="inbound",
        from_email="sender@example.com",
        to_email="brian@sapphire-pools.com",
        subject="test",
        body="inbound body",
        status=status,
        draft_response=draft,
        final_response=final,
        thread_id=thread_id,
        received_at=received_at,
        sent_at=received_at if status in ("sent", "auto_sent") else None,
        approved_at=received_at if status in ("sent", "auto_sent", "handled") else None,
    )
    db.add(m)
    await db.flush()
    return m


@pytest.mark.asyncio
async def test_port_maps_all_status_scenarios(db_session, org_a):
    """One message per scenario; assert proposal + correction rows match derivation table."""
    t = await _mk_thread(db_session, org_a.id)

    m_accepted = await _mk_msg(db_session, org_a.id, t.id,
                               status="sent", draft="Draft body", final="Draft body")
    m_edited = await _mk_msg(db_session, org_a.id, t.id,
                             status="sent", draft="Draft body", final="Human-rewrote body")
    m_handled_dismiss = await _mk_msg(db_session, org_a.id, t.id,
                                      status="handled", draft="Never-sent draft")
    m_ignored = await _mk_msg(db_session, org_a.id, t.id,
                              status="ignored", draft="Ignored draft")
    m_pending = await _mk_msg(db_session, org_a.id, t.id,
                              status="pending", draft="Pending draft")
    m_auto = await _mk_msg(db_session, org_a.id, t.id,
                           status="auto_sent", draft="Auto-sent draft", final="Auto-sent draft")
    await db_session.commit()

    counts = await port(db_session, org_id=org_a.id, dry_run=False)

    assert counts["total"] == 6
    assert counts["created_proposal"] == 6
    assert counts["parity_ok"] is True
    assert counts["by_proposal_status"][STATUS_ACCEPTED] == 2  # sent-unchanged + auto_sent
    assert counts["by_proposal_status"][STATUS_EDITED] == 1
    assert counts["by_proposal_status"][STATUS_REJECTED] == 2  # handled-no-final + ignored
    assert counts["by_proposal_status"][STATUS_STAGED] == 1
    assert counts["by_correction_type"]["acceptance"] == 2
    assert counts["by_correction_type"]["edit"] == 1
    assert counts["by_correction_type"]["rejection"] == 2

    # Spot-check the edited one: user_delta has the replace /body op.
    p_edited = (await db_session.execute(
        select(AgentProposal).where(AgentProposal.source_id == m_edited.id)
    )).scalar_one()
    assert p_edited.status == STATUS_EDITED
    assert p_edited.user_delta == [{"op": "replace", "path": "/body", "value": "Human-rewrote body"}]

    # And the pending one: staged, no correction row.
    p_pending = (await db_session.execute(
        select(AgentProposal).where(AgentProposal.source_id == m_pending.id)
    )).scalar_one()
    assert p_pending.status == STATUS_STAGED
    assert p_pending.resolved_at is None

    pending_corr = (await db_session.execute(
        select(AgentCorrection).where(AgentCorrection.source_id == p_pending.id)
    )).scalar_one_or_none()
    assert pending_corr is None


@pytest.mark.asyncio
async def test_port_is_idempotent(db_session, org_a):
    """Running twice is a no-op on the second run."""
    t = await _mk_thread(db_session, org_a.id)
    await _mk_msg(db_session, org_a.id, t.id, status="sent", draft="x", final="y")
    await _mk_msg(db_session, org_a.id, t.id, status="ignored", draft="x")
    await db_session.commit()

    first = await port(db_session, org_id=org_a.id, dry_run=False)
    assert first["created_proposal"] == 2
    assert first["skipped_already_ported"] == 0

    second = await port(db_session, org_id=org_a.id, dry_run=False)
    assert second["created_proposal"] == 0
    assert second["skipped_already_ported"] == 2
    assert second["parity_ok"] is True


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(db_session, org_a):
    t = await _mk_thread(db_session, org_a.id)
    await _mk_msg(db_session, org_a.id, t.id, status="sent", draft="x", final="x")
    await db_session.commit()

    result = await port(db_session, org_id=org_a.id, dry_run=True)
    assert result["created_proposal"] == 1  # would-be count

    n_proposals = (await db_session.execute(
        select(AgentProposal).where(AgentProposal.organization_id == org_a.id)
    )).scalars().all()
    assert len(n_proposals) == 0  # nothing persisted
