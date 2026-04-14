"""Regression fixture for InboxRulesService.

Covers the critical cutover guarantee from the inbox-rules-unification-plan:
the new rule engine must produce identical outcomes to the old split
system (inbox_routing_rules + suppressed_email_senders) for every
realistic scenario we care about.

Scenario catalog (each scenario = one test):

1. Exact sender match — sender_email equals → assign_tag
2. Domain glob match — sender_domain matches *@entrata.com → assign_folder
3. Block-replaced-with-spam — sender matches a route_to_spam rule → folder_id=spam
4. Multi-action rule — one rule emits folder + tag + suppress_prompt together
5. AND conditions — sender + subject together match; sender alone does not
6. Priority ordering — two folder-assigning rules; lower priority number wins
7. Inactive rule ignored — is_active=False skipped even if pattern matches
8. Cross-org isolation — rule in org A never matches a message in org B
9. Unknown field / operator — fail-closed (no match) rather than crash
10. Empty conditions list — treated as unconditional, always matches
11. get_sender_tag convenience helper returns the tag value
12. get_folder_for_sender resolves an assign_folder
13. get_folder_for_sender resolves route_to_spam to sentinel
14. apply() mutates thread.folder_id on assign_folder
15. apply() honors spam_folder_id for route_to_spam
16. apply() last-write-wins when two rules set different folders

The fixture is exhaustive on rule-engine behavior; downstream orchestrator
integration is tested elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.models.inbox_rule import InboxRule
from src.services.inbox_rules_service import (
    ACTION_ASSIGN_FOLDER,
    ACTION_ASSIGN_TAG,
    ACTION_ASSIGN_CATEGORY,
    ACTION_ROUTE_TO_SPAM,
    ACTION_SUPPRESS_CONTACT_PROMPT,
    InboxRulesService,
    build_context,
)


@dataclass
class FakeThread:
    """Minimal stand-in for an AgentThread (apply mutates attributes)."""
    folder_id: str | None = None
    category: str | None = None
    visibility_permission: str | None = None


async def _add_rule(db, *, org_id, name, conditions, actions, priority=100, is_active=True):
    rule = InboxRule(
        organization_id=org_id,
        name=name,
        priority=priority,
        conditions=conditions,
        actions=actions,
        is_active=is_active,
    )
    db.add(rule)
    await db.commit()
    return rule


# ---------------------------------------------------------------------------
# Evaluate — pattern matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_sender_email_match(db_session, org_a):
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="billing tag",
        conditions=[{"field": "sender_email", "operator": "equals", "value": "system@entrata.com"}],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "billing"}}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(build_context(sender_email="system@entrata.com"), org_a.id)
    assert len(actions) == 1
    assert actions[0]["type"] == ACTION_ASSIGN_TAG
    assert actions[0]["params"]["tag"] == "billing"


@pytest.mark.asyncio
async def test_sender_domain_glob_match(db_session, org_a):
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="entrata vendor folder",
        conditions=[{"field": "sender_domain", "operator": "matches", "value": "*entrata.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "vendor-folder-id"}}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(build_context(sender_email="anyone@entrata.com"), org_a.id)
    assert len(actions) == 1
    assert actions[0]["params"]["folder_id"] == "vendor-folder-id"


@pytest.mark.asyncio
async def test_route_to_spam_replaces_block(db_session, org_a):
    """Old `block` action became `route_to_spam`. Evaluate emits the action;
    apply honors the caller-supplied spam folder id."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="scppool block -> spam",
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "scppool.com"}],
        actions=[{"type": ACTION_ROUTE_TO_SPAM}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(
        build_context(sender_email="orders@scppool.com"), org_a.id
    )
    assert len(actions) == 1
    assert actions[0]["type"] == ACTION_ROUTE_TO_SPAM


@pytest.mark.asyncio
async def test_multi_action_rule(db_session, org_a):
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="utility combo",
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "utilityco.com"}],
        actions=[
            {"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "utility-folder"}},
            {"type": ACTION_ASSIGN_TAG, "params": {"tag": "utility"}},
            {"type": ACTION_SUPPRESS_CONTACT_PROMPT},
        ],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(build_context(sender_email="billing@utilityco.com"), org_a.id)
    types = [a["type"] for a in actions]
    assert types == [ACTION_ASSIGN_FOLDER, ACTION_ASSIGN_TAG, ACTION_SUPPRESS_CONTACT_PROMPT]


@pytest.mark.asyncio
async def test_and_conditions_require_all_match(db_session, org_a):
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="sender+subject",
        conditions=[
            {"field": "sender_email", "operator": "equals", "value": "alerts@monitor.io"},
            {"field": "subject", "operator": "contains", "value": "critical"},
        ],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "urgent"}}],
    )
    svc = InboxRulesService(db_session)
    # Subject missing the keyword → no match
    assert await svc.evaluate(
        build_context(sender_email="alerts@monitor.io", subject="nightly report"),
        org_a.id,
    ) == []
    # Both match → hit
    hit = await svc.evaluate(
        build_context(sender_email="alerts@monitor.io", subject="CRITICAL: disk full"),
        org_a.id,
    )
    assert len(hit) == 1


@pytest.mark.asyncio
async def test_priority_ordering(db_session, org_a):
    """Lower priority number evaluates first; its actions come out first."""
    await _add_rule(
        db_session, org_id=org_a.id, name="low prio", priority=200,
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "acme.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "low-prio-folder"}}],
    )
    await _add_rule(
        db_session, org_id=org_a.id, name="high prio", priority=50,
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "acme.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "high-prio-folder"}}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(build_context(sender_email="x@acme.com"), org_a.id)
    assert actions[0]["params"]["folder_id"] == "high-prio-folder"
    assert actions[1]["params"]["folder_id"] == "low-prio-folder"


@pytest.mark.asyncio
async def test_inactive_rule_ignored(db_session, org_a):
    await _add_rule(
        db_session, org_id=org_a.id, name="disabled", is_active=False,
        conditions=[{"field": "sender_email", "operator": "equals", "value": "x@y.com"}],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "x"}}],
    )
    svc = InboxRulesService(db_session)
    assert await svc.evaluate(build_context(sender_email="x@y.com"), org_a.id) == []


@pytest.mark.asyncio
async def test_cross_org_isolation(db_session, org_a, org_b):
    await _add_rule(
        db_session, org_id=org_a.id, name="org-a rule",
        conditions=[{"field": "sender_email", "operator": "equals", "value": "x@y.com"}],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "a"}}],
    )
    svc = InboxRulesService(db_session)
    assert await svc.evaluate(build_context(sender_email="x@y.com"), org_b.id) == []


@pytest.mark.asyncio
async def test_unknown_field_fails_closed(db_session, org_a):
    await _add_rule(
        db_session, org_id=org_a.id, name="bad",
        conditions=[{"field": "nonsense_field", "operator": "equals", "value": "whatever"}],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "oops"}}],
    )
    svc = InboxRulesService(db_session)
    assert await svc.evaluate(build_context(sender_email="x@y.com"), org_a.id) == []


@pytest.mark.asyncio
async def test_empty_conditions_always_matches(db_session, org_a):
    """An unconditional rule — useful for 'route everything from this IMAP account'."""
    await _add_rule(
        db_session, org_id=org_a.id, name="catchall",
        conditions=[],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "catchall"}}],
    )
    svc = InboxRulesService(db_session)
    assert len(await svc.evaluate(build_context(sender_email="x@y.com"), org_a.id)) == 1


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sender_tag(db_session, org_a):
    await _add_rule(
        db_session, org_id=org_a.id, name="vendor tag",
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "scppool.com"}],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "vendor"}}],
    )
    svc = InboxRulesService(db_session)
    assert await svc.get_sender_tag("orders@scppool.com", org_a.id) == "vendor"
    assert await svc.get_sender_tag("customer@example.com", org_a.id) is None


@pytest.mark.asyncio
async def test_get_folder_for_sender_assign_folder(db_session, org_a):
    await _add_rule(
        db_session, org_id=org_a.id, name="vendor folder",
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "scppool.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "vendors"}}],
    )
    svc = InboxRulesService(db_session)
    assert await svc.get_folder_for_sender("orders@scppool.com", org_a.id) == "vendors"


@pytest.mark.asyncio
async def test_get_folder_for_sender_spam_sentinel(db_session, org_a):
    await _add_rule(
        db_session, org_id=org_a.id, name="block spam sender",
        conditions=[{"field": "sender_domain", "operator": "equals", "value": "spammer.io"}],
        actions=[{"type": ACTION_ROUTE_TO_SPAM}],
    )
    svc = InboxRulesService(db_session)
    assert await svc.get_folder_for_sender("a@spammer.io", org_a.id) == "__spam__"


# ---------------------------------------------------------------------------
# Apply — mutate thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_assigns_folder(db_session, org_a):
    svc = InboxRulesService(db_session)
    t = FakeThread()
    await svc.apply(
        [{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "xyz"}}], t,
    )
    assert t.folder_id == "xyz"


@pytest.mark.asyncio
async def test_apply_spam_folder_id(db_session, org_a):
    svc = InboxRulesService(db_session)
    t = FakeThread()
    await svc.apply([{"type": ACTION_ROUTE_TO_SPAM}], t, spam_folder_id="spam-folder-id")
    assert t.folder_id == "spam-folder-id"


@pytest.mark.asyncio
async def test_apply_last_write_wins(db_session, org_a):
    svc = InboxRulesService(db_session)
    t = FakeThread()
    actions = [
        {"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "first"}},
        {"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "second"}},
    ]
    await svc.apply(actions, t)
    assert t.folder_id == "second"


@pytest.mark.asyncio
async def test_apply_assign_category(db_session, org_a):
    svc = InboxRulesService(db_session)
    t = FakeThread()
    await svc.apply(
        [{"type": ACTION_ASSIGN_CATEGORY, "params": {"category": "billing"}}], t,
    )
    assert t.category == "billing"


@pytest.mark.asyncio
async def test_apply_mark_as_read_stamps_auto_read_at(db_session, org_a):
    """mark_as_read sets auto_read_at to the thread's current
    last_message_at so the thread doesn't appear unread until a newer
    message arrives."""
    from datetime import datetime, timezone
    from src.services.inbox_rules_service import ACTION_MARK_AS_READ

    class T:
        last_message_at = datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc)
        auto_read_at = None

    svc = InboxRulesService(db_session)
    t = T()
    await svc.apply([{"type": ACTION_MARK_AS_READ}], t)
    assert t.auto_read_at == t.last_message_at


# ---------------------------------------------------------------------------
# Array value — the any-of collapse (many rules → one rule)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_value_as_list_matches_any(db_session, org_a):
    """A list-valued condition matches when the haystack matches ANY element.

    This is what lets a single rule stand in for N parallel rules — the
    cleanup pattern for migrated per-domain routing rules.
    """
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="marketing bundle → spam",
        conditions=[{
            "field": "sender_email",
            "operator": "contains",
            "value": ["mailchimp.com", "sendgrid.net", "hubspot.com"],
        }],
        actions=[{"type": ACTION_ROUTE_TO_SPAM}],
    )
    svc = InboxRulesService(db_session)

    for sender in [
        "news@mailchimp.com",
        "bounce@sendgrid.net",
        "updates@hubspot.com",
    ]:
        actions = await svc.evaluate(build_context(sender_email=sender), org_a.id)
        assert len(actions) == 1, f"expected match for {sender}"
        assert actions[0]["type"] == ACTION_ROUTE_TO_SPAM

    # A sender NOT in the list must not match.
    actions = await svc.evaluate(
        build_context(sender_email="customer@example.com"), org_a.id
    )
    assert actions == []


@pytest.mark.asyncio
async def test_value_as_list_with_equals_operator(db_session, org_a):
    """equals also works with list values — used for exact-address bundles."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="scp vendor addresses",
        conditions=[{
            "field": "sender_email",
            "operator": "equals",
            "value": ["ecom34@scppool.com", "ecom652@scppool.com"],
        }],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "vendor"}}],
    )
    svc = InboxRulesService(db_session)

    actions = await svc.evaluate(
        build_context(sender_email="ecom34@scppool.com"), org_a.id
    )
    assert len(actions) == 1
    actions = await svc.evaluate(
        build_context(sender_email="other@scppool.com"), org_a.id
    )
    assert actions == []


@pytest.mark.asyncio
async def test_empty_list_value_fails_closed(db_session, org_a):
    """[] matches nothing — safer than matching everything."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="empty bundle",
        conditions=[{"field": "sender_email", "operator": "contains", "value": []}],
        actions=[{"type": ACTION_ROUTE_TO_SPAM}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(
        build_context(sender_email="anything@example.com"), org_a.id
    )
    assert actions == []


@pytest.mark.asyncio
async def test_scalar_value_still_works(db_session, org_a):
    """Backward compat: non-list value keeps current behavior."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="single domain",
        conditions=[{"field": "sender_email", "operator": "contains", "value": "mailchimp.com"}],
        actions=[{"type": ACTION_ROUTE_TO_SPAM}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(
        build_context(sender_email="news@mailchimp.com"), org_a.id
    )
    assert len(actions) == 1


@pytest.mark.asyncio
async def test_skip_customer_match_action_fires(db_session, org_a):
    """Rule with `skip_customer_match` emits an advisory action the
    orchestrator checks to bypass the matcher's previous-match shortcut."""
    from src.services.inbox_rules_service import ACTION_SKIP_CUSTOMER_MATCH

    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="regional PM — shared sender",
        conditions=[{
            "field": "sender_email",
            "operator": "equals",
            "value": "regional@pm.example",
        }],
        actions=[{"type": ACTION_SKIP_CUSTOMER_MATCH}],
    )
    svc = InboxRulesService(db_session)
    actions = await svc.evaluate(
        build_context(sender_email="regional@pm.example"), org_a.id
    )
    assert any(a.get("type") == ACTION_SKIP_CUSTOMER_MATCH for a in actions)


@pytest.mark.asyncio
async def test_skip_customer_match_action_is_noop_in_apply(db_session, org_a):
    """apply() on a skip_customer_match action must not mutate anything —
    it's advisory, handled by the caller (orchestrator)."""
    from src.services.inbox_rules_service import ACTION_SKIP_CUSTOMER_MATCH

    class T:
        folder_id = "original-folder"
        category = "general"
        visibility_permission = None
        auto_read_at = None
        last_message_at = None

    svc = InboxRulesService(db_session)
    t = T()
    await svc.apply([{"type": ACTION_SKIP_CUSTOMER_MATCH}], t)
    assert t.folder_id == "original-folder"
    assert t.category == "general"
    assert t.visibility_permission is None
    assert t.auto_read_at is None


# ---------------------------------------------------------------------------
# customer_matched virtual field — routes by "any matched customer"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_matched_yes_when_customer_id_present(db_session, org_a):
    """Rule on customer_matched=yes fires when the thread was matched."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="clients default folder",
        conditions=[{
            "field": "customer_matched",
            "operator": "equals",
            "value": "yes",
        }],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "clients-folder"}}],
    )
    svc = InboxRulesService(db_session)

    # Matched thread — fires
    actions = await svc.evaluate(
        build_context(sender_email="a@customer.com", customer_id="cust-123"),
        org_a.id,
    )
    assert any(a.get("type") == ACTION_ASSIGN_FOLDER for a in actions)

    # Unmatched thread — does NOT fire
    actions = await svc.evaluate(
        build_context(sender_email="a@random.com"),
        org_a.id,
    )
    assert actions == []


@pytest.mark.asyncio
async def test_customer_matched_no_matches_unmatched_senders(db_session, org_a):
    """Inverse rule: customer_matched=no catches cold senders."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="tag unknown senders",
        conditions=[{
            "field": "customer_matched",
            "operator": "equals",
            "value": "no",
        }],
        actions=[{"type": ACTION_ASSIGN_TAG, "params": {"tag": "unknown"}}],
    )
    svc = InboxRulesService(db_session)

    actions = await svc.evaluate(
        build_context(sender_email="stranger@nowhere.com"),
        org_a.id,
    )
    assert any(a.get("type") == ACTION_ASSIGN_TAG for a in actions)

    actions = await svc.evaluate(
        build_context(sender_email="a@known.com", customer_id="cust-1"),
        org_a.id,
    )
    assert actions == []


# ---------------------------------------------------------------------------
# Auto-handled banner support — preview_append_match + append_sender_to_rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_returns_covered_when_existing_rule_catches_sender(db_session, org_a):
    """If a rule already catches this sender, banner shows 'covered' — no
    promotion needed, just acknowledge."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="promotions",
        conditions=[{
            "field": "sender_email",
            "operator": "contains",
            "value": ["mailchimp.com", "sendgrid.net"],
        }],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "promo-folder"}}],
    )
    svc = InboxRulesService(db_session)
    result = await svc.preview_append_match(
        org_a.id,
        sender_email="news@mailchimp.com",
        folder_id="promo-folder",
    )
    assert result["state"] == "covered"
    assert result["rule_name"] == "promotions"


@pytest.mark.asyncio
async def test_preview_returns_promotable_for_sibling_domain(db_session, org_a):
    """New sender, AI moved it to the same folder an existing rule targets
    → banner offers one-click append."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="promotions",
        conditions=[{
            "field": "sender_email",
            "operator": "contains",
            "value": ["mailchimp.com"],
        }],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "promo-folder"}}],
    )
    svc = InboxRulesService(db_session)
    result = await svc.preview_append_match(
        org_a.id,
        sender_email="newsletter@mail.bubble.io",
        folder_id="promo-folder",
    )
    assert result["state"] == "promotable"
    # operator=contains → append the domain, not the full email
    assert result["append_value"] == "mail.bubble.io"


@pytest.mark.asyncio
async def test_preview_ambiguous_when_two_rules_match_same_folder(db_session, org_a):
    """2+ rules with the same action → don't guess; fall back to unclear."""
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="rule A",
        conditions=[{"field": "sender_email", "operator": "contains", "value": "mailchimp.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "promo-folder"}}],
    )
    await _add_rule(
        db_session,
        org_id=org_a.id,
        name="rule B",
        conditions=[{"field": "sender_email", "operator": "contains", "value": "hubspot.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "promo-folder"}}],
    )
    svc = InboxRulesService(db_session)
    result = await svc.preview_append_match(
        org_a.id,
        sender_email="x@new-domain.com",
        folder_id="promo-folder",
    )
    assert result["state"] == "unclear"


@pytest.mark.asyncio
async def test_preview_unclear_when_no_matching_rule(db_session, org_a):
    """No active rule with a matching action → unclear; Create-rule fallback."""
    svc = InboxRulesService(db_session)
    result = await svc.preview_append_match(
        org_a.id,
        sender_email="anything@example.com",
        folder_id="unknown-folder",
    )
    assert result["state"] == "unclear"


@pytest.mark.asyncio
async def test_append_sender_converts_scalar_to_list(db_session, org_a):
    """Appending to a rule with a scalar value upgrades the value to a list."""
    rule = await _add_rule(
        db_session,
        org_id=org_a.id,
        name="single",
        conditions=[{"field": "sender_email", "operator": "contains", "value": "mailchimp.com"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "promo-folder"}}],
    )
    svc = InboxRulesService(db_session)
    result = await svc.append_sender_to_rule(org_a.id, rule.id, "mail.bubble.io")
    assert result["appended"] is True
    await db_session.refresh(rule)
    assert rule.conditions[0]["value"] == ["mailchimp.com", "mail.bubble.io"]


@pytest.mark.asyncio
async def test_append_sender_noop_when_already_present(db_session, org_a):
    """Appending a value already in the list is a no-op, not an error."""
    rule = await _add_rule(
        db_session,
        org_id=org_a.id,
        name="bundle",
        conditions=[{
            "field": "sender_email",
            "operator": "contains",
            "value": ["mailchimp.com", "hubspot.com"],
        }],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "promo-folder"}}],
    )
    svc = InboxRulesService(db_session)
    result = await svc.append_sender_to_rule(org_a.id, rule.id, "mailchimp.com")
    assert result["already"] is True
    assert result["appended"] is False


@pytest.mark.asyncio
async def test_append_sender_rejects_rule_without_sender_condition(db_session, org_a):
    """Rules with subject/body-only conditions shouldn't silently gain senders."""
    rule = await _add_rule(
        db_session,
        org_id=org_a.id,
        name="subject-only",
        conditions=[{"field": "subject", "operator": "contains", "value": "invoice"}],
        actions=[{"type": ACTION_ASSIGN_FOLDER, "params": {"folder_id": "f"}}],
    )
    svc = InboxRulesService(db_session)
    with pytest.raises(ValueError):
        await svc.append_sender_to_rule(org_a.id, rule.id, "x@example.com")
