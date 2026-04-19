"""Tests for the org-scoped proposal actions service logic.

The HTTP endpoints in src/api/v1/proposals.py are thin wrappers around
ProposalService; the routing + org-scope check is the only thing the
endpoints add on top of the service. Tests here verify that org-scope
check directly without standing up the full FastAPI app (which trips
test-DB table-creation ordering).

Full HTTP-layer verification runs live against the deployed backend —
see the Phase 2 Step 8 verify script in the commit.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.api.v1.proposals import _load_org_scoped
from src.models.agent_proposal import STATUS_STAGED
from src.services.proposals import ProposalService


class _FakeCtx:
    """Stand-in for OrgUserContext that the endpoint helper uses."""
    def __init__(self, organization_id: str):
        self.organization_id = organization_id


async def _seed_env(db, org):
    """Water feature inside `org` so equipment_item creators resolve."""
    from src.models.customer import Customer
    from src.models.property import Property
    from src.models.water_feature import WaterFeature
    cust = Customer(
        id=str(uuid.uuid4()), organization_id=org.id,
        first_name="A", last_name="B",
        email=f"{uuid.uuid4().hex[:6]}@t.com", customer_type="residential",
    )
    db.add(cust)
    prop = Property(
        id=str(uuid.uuid4()), organization_id=org.id, customer_id=cust.id,
        address="1 Test", city="S", state="CA", zip_code="95814",
    )
    db.add(prop)
    wf = WaterFeature(
        id=str(uuid.uuid4()), organization_id=org.id, property_id=prop.id,
        water_type="pool",
    )
    db.add(wf)
    await db.flush()
    return wf.id


async def _stage(db, org_id: str, wf_id: str) -> str:
    p = await ProposalService(db).stage(
        org_id=org_id, agent_type="test_api",
        entity_type="equipment_item",
        source_type="test", source_id=None,
        proposed_payload={
            "water_feature_id": wf_id,
            "equipment_type": "pump",
            "brand": "Pentair",
            "model": "X",
        },
    )
    return p.id


@pytest.mark.asyncio
async def test_load_org_scoped_returns_proposal_in_same_org(db_session, org_a):
    wf_id = await _seed_env(db_session, org_a)
    pid = await _stage(db_session, org_a.id, wf_id)
    await db_session.commit()

    ctx = _FakeCtx(organization_id=org_a.id)
    p = await _load_org_scoped(db_session, pid, ctx)
    assert p.id == pid
    assert p.status == STATUS_STAGED


@pytest.mark.asyncio
async def test_load_org_scoped_blocks_cross_org(db_session, org_a, org_b):
    """Proposal in org_b, caller is org_a → 404 (not 403, to avoid
    leaking existence)."""
    wf_id = await _seed_env(db_session, org_b)
    pid = await _stage(db_session, org_b.id, wf_id)
    await db_session.commit()

    ctx = _FakeCtx(organization_id=org_a.id)
    with pytest.raises(HTTPException) as exc:
        await _load_org_scoped(db_session, pid, ctx)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_load_org_scoped_404_for_missing_id(db_session, org_a):
    ctx = _FakeCtx(organization_id=org_a.id)
    with pytest.raises(HTTPException) as exc:
        await _load_org_scoped(db_session, "nonexistent-id", ctx)
    assert exc.value.status_code == 404
