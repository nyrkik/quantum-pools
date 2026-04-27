"""Tests for the no-auto-draft gate (orchestrator).

Categories in NO_AUTO_DRAFT_CATEGORIES MUST never produce a classifier
draft regardless of what the model returned. Humans reply to those
threads with verified figures.
"""

from __future__ import annotations

from src.services.agents.orchestrator import (
    NO_AUTO_DRAFT_CATEGORIES,
    _gated_draft,
)


def test_billing_in_no_auto_draft_set():
    assert "billing" in NO_AUTO_DRAFT_CATEGORIES


def test_billing_draft_is_suppressed():
    """Even if the model returns a draft, the gate strips it for
    billing — no customer-facing AI response on financial threads."""
    assert _gated_draft("billing", "Hi, your invoice is paid in full.") is None
    assert _gated_draft("billing", "") is None
    assert _gated_draft("billing", None) is None


def test_non_billing_drafts_pass_through():
    """Other categories keep whatever the classifier produced."""
    assert _gated_draft("schedule", "We can move you to Tuesday.") == "We can move you to Tuesday."
    assert _gated_draft("complaint", "draft here") == "draft here"
    assert _gated_draft("general", "") == ""
    assert _gated_draft("general", None) is None


def test_unknown_category_passes_through():
    """Defensive: a category outside the whitelist isn't auto-suppressed.
    If a future category should suppress, add it explicitly."""
    assert _gated_draft("future_category", "draft") == "draft"
    assert _gated_draft(None, "draft") == "draft"
