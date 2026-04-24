"""Regression guard: auto-send was removed 2026-04-14.

See docs/auto-send-removal-plan.md and memory feedback_no_auto_send.md.

Even acknowledgments imply human engagement. AI drafts every reply; humans
always send via one-click approve. If these assertions fail, someone has
started re-introducing the auto-send code path — revert and re-read the
memory entry before proceeding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ORCHESTRATOR = Path(__file__).parent.parent / "src/services/agents/orchestrator.py"


def test_orchestrator_never_sets_auto_sent_status():
    code = ORCHESTRATOR.read_text()
    assert 'status = "auto_sent"' not in code
    assert "status = 'auto_sent'" not in code


def test_orchestrator_has_no_commitment_phrase_guard():
    code = ORCHESTRATOR.read_text()
    assert "COMMITMENT_PHRASES" not in code
    assert "commitment_phrase" not in code


def test_orchestrator_does_not_reference_org_auto_send_flag():
    code = ORCHESTRATOR.read_text()
    assert "email_auto_send_enabled" not in code


@pytest.mark.asyncio
async def test_inbound_marked_auto_sendable_stays_pending(db_session, org_a):
    """Messages the classifier flags as low-urgency (needs_approval=False)
    must stay in status='pending', waiting for a human to accept the
    staged `email_reply` proposal from the inbox UI.

    Post-Phase-5b the draft body lives on `agent_proposals.proposed_payload.body`
    (not `AgentMessage.draft_response` — column dropped). This test verifies
    the no-auto-send invariant: inbound stays pending, no outbound row is
    created automatically.
    """
    import uuid

    from sqlalchemy import select

    from src.models.agent_message import AgentMessage

    msg = AgentMessage(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        from_email="customer@example.com",
        to_email="contact@sapphire-pools.com",
        subject="Thanks",
        body="Thanks, got it.",
        direction="inbound",
        status="pending",
    )
    db_session.add(msg)
    await db_session.commit()

    # Simulate the orchestrator's post-classification handling of a
    # "needs_approval=False" message under the new regime: no code path
    # transitions inbound messages to auto_sent and no outbound row is created.
    persisted = (await db_session.execute(
        select(AgentMessage).where(AgentMessage.id == msg.id)
    )).scalar_one()
    assert persisted.status == "pending"

    outbound = (await db_session.execute(
        select(AgentMessage).where(
            AgentMessage.organization_id == org_a.id,
            AgentMessage.direction == "outbound",
        )
    )).scalars().all()
    assert outbound == []
