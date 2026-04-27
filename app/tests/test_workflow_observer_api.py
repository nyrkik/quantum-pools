"""Tests for the workflow_observer mute API (Phase 6 step 10).

Coverage:
- Router registers the three mute endpoints
- mute → unmute round-trip persists on org_workflow_config
- Mute is idempotent — re-muting an already-muted detector updates
  timestamps without error
- Unmute is idempotent — non-existent detector is a no-op success
- Permission gating: workflow.review required (covered by checking the
  dep maps unauthorized to 403)
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.api.deps import OrgUserContext, require_permissions
from src.api.v1.workflow import (
    list_observer_mutes,
    mute_observer_detector,
    router as workflow_router,
    unmute_observer_detector,
)
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.org_workflow_config import OrgWorkflowConfig
from src.models.permission import Permission
from src.models.user import User


def test_router_exposes_observer_mute_paths():
    paths = {r.path for r in workflow_router.routes}
    assert "/workflow/observer-mutes" in paths
    assert "/workflow/observer-mutes/{detector_id}" in paths


async def _seed_user(db, org_id: str, role: OrgRole = OrgRole.owner) -> OrgUserContext:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"wfo-{uid[:8]}@t.com",
        hashed_password="x", first_name="O", last_name="M", is_active=True,
    ))
    org_user = OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_id, user_id=uid, role=role,
    )
    db.add(org_user)
    await db.flush()
    user = await db.get(User, uid)
    return OrgUserContext(user=user, org_user=org_user, org_name="Test")


@pytest.mark.asyncio
async def test_mute_then_unmute_round_trip(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()

    # No row yet — list returns empty
    pre = await list_observer_mutes(ctx=ctx, db=db_session)
    assert pre["mutes"] == {}

    # Mute creates the row + adds the detector
    out_mute = await mute_observer_detector(
        detector_id="default_assignee", ctx=ctx, db=db_session,
    )
    assert out_mute["muted"] is True
    assert "default_assignee" in out_mute["mutes"]
    assert out_mute["mutes"]["default_assignee"]["muted_by_user_id"] == ctx.user.id

    row = await db_session.get(OrgWorkflowConfig, org_a.id)
    assert row is not None
    assert "default_assignee" in row.observer_mutes

    # Unmute removes
    out_unmute = await unmute_observer_detector(
        detector_id="default_assignee", ctx=ctx, db=db_session,
    )
    assert out_unmute["muted"] is False
    assert "default_assignee" not in out_unmute["mutes"]


@pytest.mark.asyncio
async def test_mute_is_idempotent(db_session, org_a):
    """Re-muting an already-muted detector overwrites timestamps without
    erroring. Useful when a UI optimistically toggles repeatedly."""
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()

    first = await mute_observer_detector(
        detector_id="handler_mismatch", ctx=ctx, db=db_session,
    )
    second = await mute_observer_detector(
        detector_id="handler_mismatch", ctx=ctx, db=db_session,
    )
    # Both succeed; only the latest entry is in the dict.
    assert first["muted"] is True
    assert second["muted"] is True
    assert "handler_mismatch" in second["mutes"]


@pytest.mark.asyncio
async def test_unmute_nonexistent_is_noop(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()
    out = await unmute_observer_detector(
        detector_id="never_was_muted", ctx=ctx, db=db_session,
    )
    assert out["muted"] is False


@pytest.mark.asyncio
async def test_mute_rejects_invalid_detector_id(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id)
    await db_session.commit()
    with pytest.raises(HTTPException) as excinfo:
        await mute_observer_detector(detector_id="", ctx=ctx, db=db_session)
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_mute_endpoints_require_workflow_review_permission(db_session, org_a):
    """Manager role doesn't have workflow.review by default; the dep 403s."""
    perm = Permission(
        id=str(uuid.uuid4()),
        slug="workflow.review",
        resource="workflow",
        action="review",
        description="Review workflow_observer suggestions",
    )
    db_session.add(perm)
    ctx = await _seed_user(db_session, org_a.id, role=OrgRole.manager)
    await db_session.commit()

    dep = require_permissions("workflow.review")
    with pytest.raises(HTTPException) as excinfo:
        await dep(ctx=ctx, db=db_session)
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["permission"] == "workflow.review"
