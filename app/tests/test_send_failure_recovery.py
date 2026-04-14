"""Tests for FB-24-class send-failure recovery.

When ANY exception happens during outbound send, the message must end up
status='failed' with delivery_error captured. Without this, sends crash
silently and customers don't get email while the sender thinks it went out.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_record_outbound_send_failure_creates_failed_row(db_session, org_a):
    """The shared helper must persist a failed outbound row + delivery_error."""
    from sqlalchemy import select
    from src.models.agent_message import AgentMessage
    from src.services.agents.send_failure import record_outbound_send_failure

    await record_outbound_send_failure(
        db_session,
        org_id=org_a.id,
        thread_id=None,
        from_email="us@test.com",
        to_email="them@test.com",
        subject="Test",
        body="Body",
        error="NameError: simulated crash",
        matched_customer_id=None,
        customer_name=None,
    )

    row = (await db_session.execute(
        select(AgentMessage).where(
            AgentMessage.organization_id == org_a.id,
            AgentMessage.to_email == "them@test.com",
        )
    )).scalar_one_or_none()
    assert row is not None
    assert row.status == "failed"
    assert row.delivery_error is not None
    assert "NameError" in row.delivery_error
    assert row.direction == "outbound"


@pytest.mark.asyncio
async def test_record_outbound_send_failure_truncates_long_error(db_session, org_a):
    """delivery_error column is String(500). A very long exception string
    must not crash the helper."""
    from sqlalchemy import select
    from src.models.agent_message import AgentMessage
    from src.services.agents.send_failure import record_outbound_send_failure

    long_err = "A" * 5000
    await record_outbound_send_failure(
        db_session,
        org_id=org_a.id,
        thread_id=None,
        from_email="us@test.com",
        to_email="long@test.com",
        subject="x",
        body="x",
        error=long_err,
    )

    row = (await db_session.execute(
        select(AgentMessage).where(
            AgentMessage.organization_id == org_a.id,
            AgentMessage.to_email == "long@test.com",
        )
    )).scalar_one_or_none()
    assert row is not None
    assert len(row.delivery_error) <= 500


@pytest.mark.asyncio
async def test_record_outbound_send_failure_no_error_text(db_session, org_a):
    """Empty error string still produces a usable failed row."""
    from sqlalchemy import select
    from src.models.agent_message import AgentMessage
    from src.services.agents.send_failure import record_outbound_send_failure

    await record_outbound_send_failure(
        db_session,
        org_id=org_a.id,
        thread_id=None,
        from_email="us@test.com",
        to_email="empty@test.com",
        subject="x",
        body="x",
        error="",
    )

    row = (await db_session.execute(
        select(AgentMessage).where(
            AgentMessage.organization_id == org_a.id,
            AgentMessage.to_email == "empty@test.com",
        )
    )).scalar_one_or_none()
    assert row is not None
    assert row.delivery_error  # falls back to "unknown send error"
