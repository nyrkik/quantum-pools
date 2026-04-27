"""Tests for thread_utils.normalize_subject + make_thread_key.

FB-57 root cause: the normalizer stripped one leading `Re:` but left
`[EXTERNAL]`, so a reply chain with corporate tags split into a new
thread instead of appending. These tests pin the fix.
"""

from __future__ import annotations

import pytest

from src.utils.thread_utils import make_thread_key, normalize_subject


# ---------------------------------------------------------------------------
# Reply/forward prefix stripping (existing behavior, regression-pinned)
# ---------------------------------------------------------------------------


def test_strips_single_re():
    assert normalize_subject("Re: Hello") == "Hello"


def test_strips_multiple_re():
    assert normalize_subject("Re: Re: Re: Hello") == "Hello"


def test_strips_fwd_and_fw():
    assert normalize_subject("Fwd: Hello") == "Hello"
    assert normalize_subject("Fw: Hello") == "Hello"


def test_case_insensitive_prefix_match():
    assert normalize_subject("RE: hello") == "hello"
    assert normalize_subject("FWD: hello") == "hello"


def test_no_prefix_unchanged():
    assert normalize_subject("Hello") == "Hello"


def test_empty_subject():
    assert normalize_subject("") == ""
    assert normalize_subject(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bracketed corporate-tag stripping (FB-57 fix)
# ---------------------------------------------------------------------------


def test_strips_external_tag():
    assert normalize_subject("[EXTERNAL] Hello") == "Hello"


def test_strips_ext_tag():
    assert normalize_subject("[EXT] Hello") == "Hello"


def test_strips_secure_tag():
    assert normalize_subject("[SECURE] Hello") == "Hello"


def test_strips_unknown_bracket_tag():
    """Any bracketed prefix qualifies — corporate tags are arbitrary."""
    assert normalize_subject("[CompanyXYZ-Compliance] Hello") == "Hello"


def test_does_not_strip_inline_brackets():
    """Brackets WITHIN the subject body must survive."""
    assert normalize_subject("Quote for [Pinebrook Village]") == "Quote for [Pinebrook Village]"


def test_does_not_strip_oversized_brackets():
    """Cap at 40 chars — anything longer is real content, not a tag."""
    long_tag = "[" + "x" * 50 + "] Hello"
    assert normalize_subject(long_tag) == long_tag  # untouched


# ---------------------------------------------------------------------------
# Stacked prefixes (the FB-57 reproduction)
# ---------------------------------------------------------------------------


def test_fb57_real_example():
    """The actual subjects that broke threading on Sapphire 2026-04-27."""
    original = "The Madison - Permit (Pool)"
    reply = "Re: [EXTERNAL] Re: The Madison - Permit (Pool)"
    assert normalize_subject(original) == "The Madison - Permit (Pool)"
    assert normalize_subject(reply) == "The Madison - Permit (Pool)"
    # And via the full thread key:
    assert make_thread_key("madisonmgr@greystar.com", original) \
        == make_thread_key("madisonmgr@greystar.com", reply)


def test_stacks_arbitrary_order():
    cases = [
        "Re: [EXTERNAL] Hello",
        "[EXTERNAL] Re: Hello",
        "[EXT] Re: [SECURE] Hello",
        "Re: Re: [EXTERNAL] Re: Hello",
        "  Re:   [EXT]   Re:   Hello  ",  # whitespace tolerance
    ]
    for c in cases:
        assert normalize_subject(c) == "Hello", f"failed: {c!r}"


def test_make_thread_key_lowercases_for_db_uniqueness():
    """Thread keys are stored lowercased — case in the contact email or
    subject must not produce duplicate threads."""
    a = make_thread_key("MadisonMgr@Greystar.com", "Re: Hello")
    b = make_thread_key("madisonmgr@greystar.com", "hello")
    assert a == b
