"""Phase 4 — `assigned_to=unassigned` sentinel filter on list_actions.

Guards the Unassigned filter chip on /jobs: the chip hits
`GET /v1/admin/agent-actions?assigned_to=unassigned`, and the service
must translate that to `WHERE assigned_to IS NULL`. A real first_name
of "unassigned" is not possible (no user is literally named that),
and the alternative (a separate `unassigned=true` query param)
duplicates chip state on the frontend for no benefit.
"""

from __future__ import annotations

import uuid

import pytest

from src.models.agent_action import AgentAction
from src.services.agent_action_service import AgentActionService


@pytest.mark.asyncio
async def test_list_actions_unassigned_sentinel_returns_null_assignee_only(
    db_session, org_a,
):
    uid = str(uuid.uuid4())
    db_session.add_all([
        AgentAction(
            id=str(uuid.uuid4()),
            organization_id=org_a.id,
            description="Unassigned",
            action_type="follow_up",
            status="open",
            assigned_to=None,
        ),
        AgentAction(
            id=uid,
            organization_id=org_a.id,
            description="Assigned to Kim",
            action_type="follow_up",
            status="open",
            assigned_to="Kim",
        ),
    ])
    await db_session.commit()

    rows = await AgentActionService(db_session).list_actions(
        org_id=org_a.id, assigned_to="unassigned",
    )
    assert {r["description"] for r in rows} == {"Unassigned"}

    # And the real-name path still works (regression guard).
    rows_kim = await AgentActionService(db_session).list_actions(
        org_id=org_a.id, assigned_to="Kim",
    )
    assert {r["description"] for r in rows_kim} == {"Assigned to Kim"}
