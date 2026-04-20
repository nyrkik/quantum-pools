"""Tests for Phase 4 workflow handlers.

Covers:
- Registry: all 3 handlers register, `get_handler` lookup works,
  unknown handler raises KeyError.
- Each handler's `next_step_for` returns a NextStep with the expected
  shape, including edge cases:
    * assign_inline uses fallback_user_id when no prior assignments
    * assign_inline drops a stale default not in the options list
    * unassigned_pool counts only open + unassigned jobs
    * schedule_inline returns an ISO `default_date` in the future
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models.agent_action import AgentAction
from src.models.org_workflow_config import OrgWorkflowConfig
from src.models.organization_user import OrganizationUser
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.workflow import HANDLERS, get_handler
from src.services.workflow.handlers.assign_inline import AssignInlineHandler
from src.services.workflow.handlers.schedule_inline import ScheduleInlineHandler
from src.services.workflow.handlers.unassigned_pool import UnassignedPoolHandler


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    db, org_id: str, *, role: str = "manager", first_name: str = "Test",
) -> str:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid,
        email=f"wf-{uid[:8]}@test.com",
        hashed_password="x",
        first_name=first_name,
        last_name="User",
        is_active=True,
    ))
    db.add(OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        user_id=uid,
        role=role,
    ))
    await db.flush()
    return uid


async def _seed_action(
    db, org_id: str, *, assigned_to: str | None = None, status: str = "open",
) -> AgentAction:
    a = AgentAction(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        action_type="service",
        description="Test job",
        status=status,
        assigned_to=assigned_to,
    )
    db.add(a)
    await db.flush()
    return a


def _actor(user_id: str | None = None) -> Actor:
    return Actor(actor_type="user", user_id=user_id)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_all_three_handlers_register():
    assert set(HANDLERS) == {"assign_inline", "unassigned_pool", "schedule_inline"}


def test_get_handler_returns_registered_instance():
    h = get_handler("assign_inline")
    assert h.name == "assign_inline"
    assert h.entity_types == ("job",)


def test_get_handler_unknown_raises_with_hint():
    with pytest.raises(KeyError) as excinfo:
        get_handler("nope")
    # Error message includes the known handlers so misconfigurations are actionable.
    assert "assign_inline" in str(excinfo.value)


# ---------------------------------------------------------------------------
# assign_inline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_inline_returns_options_and_no_default_when_none(db_session, org_a):
    """New org, no prior assignments, no fallback → default is None and
    options include all active org users."""
    uid = await _seed_user(db_session, org_a.id, role="manager", first_name="Kim")
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await AssignInlineHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid), db=db_session,
    )
    assert step is not None
    assert step.kind == "assign_inline"
    assert step.initial["entity_type"] == "job"
    assert step.initial["entity_id"] == action.id
    assert step.initial["default_assignee_id"] is None
    assert {o["id"] for o in step.initial["assignee_options"]} == {uid}


@pytest.mark.asyncio
async def test_assign_inline_last_used_in_org_default(db_session, org_a):
    uid_actor = await _seed_user(db_session, org_a.id, first_name="Brian")
    uid_other = await _seed_user(db_session, org_a.id, first_name="Kim")
    # Prior assignment to "Kim" — most recent one wins.
    await _seed_action(db_session, org_a.id, assigned_to=uid_other)
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await AssignInlineHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid_actor), db=db_session,
    )
    assert step.initial["default_assignee_id"] == uid_other


@pytest.mark.asyncio
async def test_assign_inline_fixed_strategy_uses_fallback(db_session, org_a):
    uid_actor = await _seed_user(db_session, org_a.id, first_name="Brian")
    uid_fallback = await _seed_user(db_session, org_a.id, first_name="Kim")
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "assign_inline"},
        default_assignee_strategy={
            "strategy": "fixed", "fallback_user_id": uid_fallback,
        },
    ))
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await AssignInlineHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid_actor), db=db_session,
    )
    assert step.initial["default_assignee_id"] == uid_fallback


@pytest.mark.asyncio
async def test_assign_inline_always_ask_returns_no_default(db_session, org_a):
    uid = await _seed_user(db_session, org_a.id)
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "assign_inline"},
        default_assignee_strategy={"strategy": "always_ask"},
    ))
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await AssignInlineHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid), db=db_session,
    )
    assert step.initial["default_assignee_id"] is None


@pytest.mark.asyncio
async def test_assign_inline_drops_stale_default_not_in_options(db_session, org_a):
    """If the strategy resolves to a user who left the org (not in
    assignee_options), the default is cleared so the picker doesn't
    pre-select a missing user."""
    uid_alive = await _seed_user(db_session, org_a.id, first_name="Brian")
    stale_uid = str(uuid.uuid4())  # not in org_users at all
    db_session.add(OrgWorkflowConfig(
        organization_id=org_a.id,
        post_creation_handlers={"job": "assign_inline"},
        default_assignee_strategy={
            "strategy": "fixed", "fallback_user_id": stale_uid,
        },
    ))
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await AssignInlineHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid_alive), db=db_session,
    )
    assert step.initial["default_assignee_id"] is None
    assert {o["id"] for o in step.initial["assignee_options"]} == {uid_alive}


@pytest.mark.asyncio
async def test_assign_inline_returns_none_for_wrong_entity(db_session, org_a):
    # Pass some non-AgentAction object — handler should noop rather than crash.
    step = await AssignInlineHandler().next_step_for(
        created="not-an-action", org_id=org_a.id, actor=_actor(None), db=db_session,
    )
    assert step is None


# ---------------------------------------------------------------------------
# unassigned_pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unassigned_pool_counts_only_open_unassigned(db_session, org_a):
    uid = await _seed_user(db_session, org_a.id)
    # 2 unassigned open jobs + 1 assigned + 1 done (both filtered out)
    await _seed_action(db_session, org_a.id)  # open, unassigned
    await _seed_action(db_session, org_a.id)  # open, unassigned
    await _seed_action(db_session, org_a.id, assigned_to=uid)  # assigned
    await _seed_action(db_session, org_a.id, status="done")  # closed
    new_action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await UnassignedPoolHandler().next_step_for(
        created=new_action, org_id=org_a.id, actor=_actor(uid), db=db_session,
    )
    assert step is not None
    assert step.kind == "unassigned_pool"
    assert step.initial["entity_id"] == new_action.id
    # new_action + the 2 prior unassigned-open = 3 waiting.
    assert step.initial["pool_count"] == 3


@pytest.mark.asyncio
async def test_unassigned_pool_other_org_excluded(db_session, org_a, org_b):
    uid = await _seed_user(db_session, org_a.id)
    # A pile of unassigned jobs in org_b — should not count.
    for _ in range(5):
        await _seed_action(db_session, org_b.id)
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await UnassignedPoolHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid), db=db_session,
    )
    assert step.initial["pool_count"] == 1


# ---------------------------------------------------------------------------
# schedule_inline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_inline_includes_default_date_in_future(db_session, org_a):
    uid = await _seed_user(db_session, org_a.id)
    action = await _seed_action(db_session, org_a.id)
    await db_session.commit()

    step = await ScheduleInlineHandler().next_step_for(
        created=action, org_id=org_a.id, actor=_actor(uid), db=db_session,
    )
    assert step is not None
    assert step.kind == "schedule_inline"
    # default_date is ISO format and in the future.
    dt = datetime.fromisoformat(step.initial["default_date"])
    assert dt.tzinfo is not None
    assert dt > datetime.now(timezone.utc)
    # Assignee scaffold is present.
    assert "assignee_options" in step.initial
