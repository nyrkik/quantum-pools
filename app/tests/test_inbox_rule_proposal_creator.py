"""Tests for the inbox_rule proposal creator (Phase 6 step 3).

Verifies:
- Stage-time validation rejects malformed rules (sender_domain @-values,
  unknown action types, empty action list)
- Accept creates an InboxRule row with the supplied conditions/actions
- describe_rule renders common shapes in plain language
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from src.models.inbox_rule import InboxRule
from src.models.user import User
from src.services.events.platform_event_service import Actor
from src.services.proposals import ProposalService
from src.services.proposals.creators.inbox_rule import (
    InboxRuleProposalPayload,
    describe_rule,
)


async def _seed_user(db) -> str:
    u = User(
        id=str(uuid.uuid4()),
        email=f"ir-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="x", first_name="Inbox", last_name="Tester",
    )
    db.add(u)
    await db.flush()
    return u.id


# ---------------------------------------------------------------------------
# Stage-time validation
# ---------------------------------------------------------------------------


def test_stage_rejects_sender_domain_with_at_sign():
    """The sender_domain @-value class-of-bug guard fires at stage time
    (and again at accept time) — agent output that violates this can
    never persist."""
    with pytest.raises(ValidationError):
        InboxRuleProposalPayload(
            conditions=[{
                "field": "sender_domain",
                "operator": "equals",
                "value": "@scppool.com",
            }],
            actions=[{"type": "assign_folder", "params": {"folder_key": "spam"}}],
        )


def test_stage_rejects_unknown_action_type():
    with pytest.raises(ValidationError):
        InboxRuleProposalPayload(
            conditions=[{
                "field": "sender_email", "operator": "equals", "value": "x@y.com"
            }],
            actions=[{"type": "delete_thread", "params": {}}],
        )


def test_stage_rejects_empty_actions():
    with pytest.raises(ValidationError):
        InboxRuleProposalPayload(
            conditions=[{
                "field": "sender_email", "operator": "equals", "value": "x@y.com"
            }],
            actions=[],
        )


# ---------------------------------------------------------------------------
# Accept end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_creates_inbox_rule(db_session, org_a):
    user_id = await _seed_user(db_session)
    await db_session.commit()

    service = ProposalService(db_session)
    p = await service.stage(
        org_id=org_a.id,
        agent_type="workflow_observer",
        entity_type="inbox_rule",
        source_type="organization",
        source_id=org_a.id,
        proposed_payload={
            "name": "Acme billing → category=billing",
            "conditions": [
                {"field": "sender_domain", "operator": "equals", "value": "acme.com"},
            ],
            "actions": [
                {"type": "assign_category", "params": {"category": "billing"}},
            ],
            "is_active": True,
        },
    )
    await db_session.commit()

    actor = Actor(actor_type="user", user_id=user_id)
    p_resolved, rule = await service.accept(proposal_id=p.id, actor=actor)
    await db_session.commit()

    assert p_resolved.status == "accepted"
    assert p_resolved.outcome_entity_type == "inbox_rule"
    assert p_resolved.outcome_entity_id == rule.id

    refreshed = await db_session.get(InboxRule, rule.id)
    assert refreshed is not None
    assert refreshed.name == "Acme billing → category=billing"
    assert refreshed.conditions[0]["field"] == "sender_domain"
    assert refreshed.actions[0]["type"] == "assign_category"
    assert refreshed.is_active is True


# ---------------------------------------------------------------------------
# Plain-language renderer
# ---------------------------------------------------------------------------


def test_describe_rule_simple_category():
    payload = {
        "conditions": [
            {"field": "sender_domain", "operator": "equals", "value": "acme.com"},
        ],
        "actions": [
            {"type": "assign_category", "params": {"category": "billing"}},
        ],
    }
    desc = describe_rule(payload)
    assert "sender domain is \"acme.com\"" in desc
    assert "category to \"billing\"" in desc


def test_describe_rule_multiple_conditions_and_actions():
    payload = {
        "conditions": [
            {"field": "sender_email", "operator": "contains", "value": "newsletter"},
            {"field": "subject", "operator": "starts_with", "value": "[promo]"},
        ],
        "actions": [
            {"type": "assign_folder", "params": {"folder_key": "marketing"}},
            {"type": "mark_as_read", "params": {}},
        ],
    }
    desc = describe_rule(payload)
    assert "sender contains \"newsletter\"" in desc
    assert "subject starts with \"[promo]\"" in desc
    assert "folder \"marketing\"" in desc
    assert "mark as read" in desc


def test_describe_rule_list_value_renders_compactly():
    payload = {
        "conditions": [
            {"field": "sender_domain", "operator": "equals",
             "value": ["a.com", "b.com", "c.com", "d.com"]},
        ],
        "actions": [{"type": "route_to_spam", "params": {}}],
    }
    desc = describe_rule(payload)
    # 4 values → "a.com" or 3 more
    assert "or 3 more" in desc


def test_describe_rule_unknown_action_falls_back_gracefully():
    """describe_rule never raises — unknown action types render as text."""
    payload = {
        "conditions": [{"field": "subject", "operator": "contains", "value": "x"}],
        "actions": [{"type": "future_action_v3", "params": {"foo": "bar"}}],
    }
    desc = describe_rule(payload)
    assert "future_action_v3" in desc
