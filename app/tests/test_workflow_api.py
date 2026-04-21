"""Smoke-test for the workflow config API (Phase 4 Step 4).

The HTTP endpoints are thin wrappers around WorkflowConfigService
(already covered by test_workflow_config_service.py). This file
verifies:
- router mounts cleanly
- PUT is gated by `workflow.manage_config` (403 for roles without it)
- invalid handler in the body maps to 422 (not 500)
- GET is not gated (any org user can read)
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.api.deps import OrgUserContext, require_permissions
from src.api.v1.workflow import (
    WorkflowConfigBody,
    get_workflow_config,
    list_handlers,
    put_workflow_config,
    router as workflow_router,
)
from src.models.organization_user import OrgRole, OrganizationUser
from src.models.permission import Permission
from src.models.user import User
from src.models.user_permission_override import UserPermissionOverride


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------


def test_router_exposes_expected_paths():
    paths = {r.path for r in workflow_router.routes}
    assert "/workflow/config" in paths
    assert "/workflow/handlers" in paths


@pytest.mark.asyncio
async def test_list_handlers_returns_registry(db_session, org_a):
    # Build a minimal OrgUserContext for the endpoint.
    uid = str(uuid.uuid4())
    user = User(
        id=uid, email=f"wfl-{uid[:8]}@t.com",
        hashed_password="x", first_name="A", last_name="B",
        is_active=True,
    )
    db_session.add(user)
    org_user = OrganizationUser(
        id=str(uuid.uuid4()),
        organization_id=org_a.id, user_id=uid, role=OrgRole.owner,
    )
    db_session.add(org_user)
    await db_session.commit()

    ctx = OrgUserContext(user=user, org_user=org_user, org_name="Test")
    out = await list_handlers(ctx)
    names = {h["name"] for h in out["handlers"]}
    assert names == {"assign_inline", "hold_for_dispatch", "schedule_inline"}


# ---------------------------------------------------------------------------
# Permission gating
# ---------------------------------------------------------------------------


async def _seed_user(
    db, org_id: str, role: OrgRole = OrgRole.manager,
) -> OrgUserContext:
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid, email=f"wfg-{uid[:8]}@t.com",
        hashed_password="x", first_name="M", last_name="G",
        is_active=True,
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
async def test_put_requires_workflow_manage_config_perm(db_session, org_a):
    """Manager role has no workflow.manage_config in the default preset
    map — require_permissions should 403."""
    # Seed the permission row (real presets load from DB, so we need
    # a row for the dep to look up).
    perm = Permission(
        id=str(uuid.uuid4()),
        slug="workflow.manage_config",
        resource="workflow",
        action="manage_config",
        description="Configure post-creation handlers",
    )
    db_session.add(perm)
    ctx = await _seed_user(db_session, org_a.id, role=OrgRole.manager)
    await db_session.commit()

    # Call the dep directly.
    dep = require_permissions("workflow.manage_config")
    with pytest.raises(HTTPException) as excinfo:
        await dep(ctx=ctx, db=db_session)
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["permission"] == "workflow.manage_config"


@pytest.mark.asyncio
async def test_put_accepts_with_override_grant(db_session, org_a):
    """A user WITHOUT the permission by role but WITH a per-user
    override grant passes the dep. Covers the "per-user grantable"
    requirement from the refinement gate."""
    perm = Permission(
        id=str(uuid.uuid4()),
        slug="workflow.manage_config",
        resource="workflow",
        action="manage_config",
        description="Configure post-creation handlers",
    )
    db_session.add(perm)
    ctx = await _seed_user(db_session, org_a.id, role=OrgRole.technician)
    await db_session.flush()
    db_session.add(UserPermissionOverride(
        id=str(uuid.uuid4()),
        org_user_id=ctx.org_user.id,
        permission_id=perm.id,
        scope="all",
        granted=True,
    ))
    await db_session.commit()

    dep = require_permissions("workflow.manage_config")
    out = await dep(ctx=ctx, db=db_session)
    assert out is ctx


# ---------------------------------------------------------------------------
# PUT body validation surfaces as 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_unknown_handler_maps_to_422(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id, role=OrgRole.owner)
    await db_session.commit()

    body = WorkflowConfigBody(
        post_creation_handlers={"job": "nonexistent_handler"},
        default_assignee_strategy={"strategy": "always_ask"},
    )
    with pytest.raises(HTTPException) as excinfo:
        await put_workflow_config(body=body, ctx=ctx, db=db_session)
    assert excinfo.value.status_code == 422
    assert "nonexistent_handler" in excinfo.value.detail


@pytest.mark.asyncio
async def test_get_returns_system_defaults_for_empty_org(db_session, org_a):
    ctx = await _seed_user(db_session, org_a.id, role=OrgRole.readonly)
    await db_session.commit()

    out = await get_workflow_config(ctx=ctx, db=db_session)
    assert out["post_creation_handlers"]["job"] == "assign_inline"
    assert out["default_assignee_strategy"]["strategy"] == "last_used_in_org"
