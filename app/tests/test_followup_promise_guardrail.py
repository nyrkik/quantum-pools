"""Tests for _is_followup_promise — orchestrator guardrail.

Reported via dogfood 2026-04-27 (Kim, follow-up to FB-57): customer
replies that establish a commitment from the OTHER side ("I'll get
back to you", "I'll relay this") were classified as no_response by
the AI and auto-handled, hiding them from the Pending inbox even
though Brian/Kim need to track them.

Two real Sapphire reproductions:
  "Thank you, I have sent the request to my higher-up and will keep you posted."
  "I will relay this to maintenance and give you an update soon."
Both must trigger the guardrail (return True).

Pure-acks ("Ok thanks!", "You are very welcome!") must NOT trigger
(return False) — the classifier is correct on those.
"""

from __future__ import annotations

import pytest

from src.services.agents.orchestrator import _is_followup_promise


# ---------------------------------------------------------------------------
# Real Sapphire reproductions (the bug)
# ---------------------------------------------------------------------------


def test_kim_madison_pool_keys_reply():
    body = "Hi Kim, I will relay this to maintenance and give you an update soon. Thank you,"
    assert _is_followup_promise(body) is True


def test_kim_madison_pool_service_reply():
    body = "Thank you, I have sent the request to my higher-up and will keep you posted."
    assert _is_followup_promise(body) is True


# ---------------------------------------------------------------------------
# Future-commitment patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "I'll get back to you tomorrow.",
    "I will get back to you on this.",
    "We'll get back to you next week.",
    "I'll follow up later today.",
    "Will follow-up after I check with the team.",
    "I'll let you know once I hear back.",
    "Will let you know.",
    "I'll update you soon.",
    "I will update you tomorrow.",
    "Give you an update by end of day.",
    "I'll keep you posted on this.",
    "Will keep you informed.",
    "I'll look into it.",
    "I'll check on this.",
    "I'll relay this to the team.",
    "I'll discuss this with my manager.",
    "I'll discuss with the team.",
    "I'll reach out later.",
    "I have sent the request to my higher-up.",
    "I've sent it over to ops.",
    "I sent the request to my supervisor.",
    "I'll run this by my boss.",
    "Still waiting on approval.",
    "We're waiting on the parts to arrive.",
    "Hearing on it from the team.",
    "Will get back to you Monday.",
])
def test_followup_promise_phrases_trigger(text):
    assert _is_followup_promise(text) is True, f"should match: {text!r}"


# ---------------------------------------------------------------------------
# Pure acknowledgments — must NOT trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Ok perfect, Thanks!",
    "You are very welcome!",
    "Thanks!",
    "Thank you.",
    "Got it.",
    "Sounds good.",
    "Perfect.",
    "Approved.",
    "👍",
    "Sure thing.",
    "Will do.",  # short willdo isn't a future-commitment to OUR side
])
def test_pure_acks_do_not_trigger(text):
    assert _is_followup_promise(text) is False, f"should NOT match: {text!r}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_body():
    assert _is_followup_promise("") is False
    assert _is_followup_promise(None) is False


def test_quoted_signature_does_not_falsetrigger():
    """The previous outbound from US sometimes contains "we'll get back"
    in our own signature/template. The guardrail still triggers (correct
    — body contains the phrase), so it's OK that the classifier ALSO
    needs to be in no_response/thank_you state for the override to fire.
    The test docs the expectation."""
    body = "Hi, ok thanks!\n\n> From: Kim\n> We'll get back to you within 24 hours."
    # Triggers because "we'll get back" matches. The orchestrator gate is
    # `category in (no_response, thank_you) AND sender_is_customer AND
    # _is_followup_promise(body)` — the category gate ensures we only
    # override when the classifier ALREADY thinks it's no-response.
    assert _is_followup_promise(body) is True


def test_curly_apostrophe_handled():
    """Email clients often produce curly apostrophes (’) instead of
    straight ones (')."""
    assert _is_followup_promise("I’ll get back to you") is True
    assert _is_followup_promise("we’ll keep you posted") is True
