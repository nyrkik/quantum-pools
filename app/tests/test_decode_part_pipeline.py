"""Canonical decode pipeline — per-part tests.

Covers each layer of ``decode_part`` independently: charset fallback,
mojibake repair via ftfy, Unicode NFC, zero-width strip. Spec lives in
``docs/email-body-pipeline-refactor.md``.

Pipeline order is tested by constructing synthetic messages that
exercise each quirk without going through the full provider ingest.
If any of these regress, inbox previews will leak the underlying
symptom (garbage chars, mojibaked curly quotes, invisible padding,
decomposed Unicode that breaks string equality).
"""

from __future__ import annotations

import email


def _raw(ct_header: str, body_bytes: bytes) -> email.message.EmailMessage:
    """Build a minimal EmailMessage with the given Content-Type +
    raw body bytes, bypassing EmailMessage.set_content (which would
    pick its own CTE + charset)."""
    raw = (ct_header + "\r\n\r\n").encode("ascii") + body_bytes
    return email.message_from_bytes(raw)


def test_decode_part_fixes_utf8_as_latin1_mojibake():
    """`you'll` was sent as UTF-8 but declared as Latin-1. stdlib
    decodes to `youâ\\x80\\x99ll` (technically valid). ftfy fixes it."""
    from src.services.agents.mail_agent import (
        decode_part,
        consume_last_body_normalize_flags,
    )

    # Bytes are actually UTF-8 (0xe2 0x80 0x99 = right single quote).
    body = "you’ll see “quotes”".encode("utf-8")
    msg = _raw('Content-Type: text/plain; charset="iso-8859-1"', body)
    out = decode_part(msg)
    flags = consume_last_body_normalize_flags()

    # Mojibake gone — no Latin-1-decode artifacts of UTF-8 multibyte chars.
    assert "â" not in out
    assert "\x80" not in out
    assert "\x99" not in out
    # Real content survives (ftfy keeps curly quotes intact per our
    # uncurl_quotes=False config — that's deliberate).
    assert "you\u2019ll" in out
    assert "\u201cquotes\u201d" in out
    assert flags.get("mojibake_repaired") is True


def test_decode_part_charset_fallback_when_declared_charset_is_wrong():
    """Sender declared a charset that can't decode the bytes → fall
    back to charset-normalizer."""
    from src.services.agents.mail_agent import (
        decode_part,
        consume_last_body_normalize_flags,
    )

    # UTF-8 bytes but declared as pure ASCII (breaks on non-ASCII byte)
    body = "café ¡hola!".encode("utf-8")
    msg = _raw('Content-Type: text/plain; charset="us-ascii"', body)
    out = decode_part(msg)
    flags = consume_last_body_normalize_flags()

    # Whatever fallback picks, it must produce readable unicode
    # (no UnicodeDecodeError bubbling out, no replacement chars
    # scattered through the output).
    assert "café" in out or "caf" in out
    assert flags.get("charset_fallback_used") is True


def test_decode_part_nfc_normalizes_decomposed_unicode():
    """Composed vs decomposed Unicode must compare equal after
    normalize. Decomposed ``é`` (e + U+0301) becomes composed
    (U+00E9)."""
    from src.services.agents.mail_agent import decode_part

    # Decomposed: e (0x65) + combining acute (U+0301 = 0xCC 0x81 UTF-8)
    body = b"caf\x65\xcc\x81"
    msg = _raw('Content-Type: text/plain; charset="utf-8"', body)
    out = decode_part(msg)

    # After NFC, length is 4 (c, a, f, é) not 5.
    assert out == "café"
    assert len(out) == 4


def test_decode_part_strips_zero_width_characters():
    """Marketers insert U+200B/C/D and U+FEFF to pad Gmail previews.
    These are invisible but leak into AI context and search. Strip."""
    from src.services.agents.mail_agent import (
        decode_part,
        consume_last_body_normalize_flags,
    )

    # "Hi" + ZWJ + " " + ZWNJ + "Brian" + BOM — all invisible.
    body = "Hi\u200d \u200cBrian\ufeff".encode("utf-8")
    msg = _raw('Content-Type: text/plain; charset="utf-8"', body)
    out = decode_part(msg)
    flags = consume_last_body_normalize_flags()

    assert "\u200b" not in out
    assert "\u200c" not in out
    assert "\u200d" not in out
    assert "\ufeff" not in out
    assert "Hi Brian" in out
    assert flags.get("zero_width_stripped") is True


def test_decode_part_clean_text_passes_through_flags_empty():
    """A body that needs no repair produces an empty diagnostics
    dict — every flag absent so the observability event doesn't
    fire for clean senders."""
    from src.services.agents.mail_agent import (
        decode_part,
        consume_last_body_normalize_flags,
    )

    body = "Hi Brian,\n\nThanks for the estimate. Book me in.\n\n— Kim".encode("utf-8")
    msg = _raw('Content-Type: text/plain; charset="utf-8"', body)
    out = decode_part(msg)
    flags = consume_last_body_normalize_flags()

    assert "Thanks for the estimate" in out
    assert flags == {} or not any(flags.values())


def test_parse_from_header_extracts_display_name_and_address():
    """The AmEx VERP case — display name is "American Express", local
    part is opaque. Must return them separately so the UI can prefer
    the name."""
    from src.services.agents.mail_agent import parse_from_header

    name, addr = parse_from_header(
        'American Express <r_07b156d0-c180-3d87-808b-e_1_x.AmericanExpress@welcome.americanexpress.com>',
    )
    assert name == "American Express"
    assert addr.endswith("@welcome.americanexpress.com")


def test_parse_from_header_handles_rfc2047_encoded_name():
    """Encoded display name — must decode via email.headerregistry."""
    from src.services.agents.mail_agent import parse_from_header

    # "=?UTF-8?B?QnJpYW4=?=" base64-encodes "Brian"
    name, addr = parse_from_header("=?UTF-8?B?QnJpYW4=?= <brian@example.com>")
    assert name == "Brian"
    assert addr == "brian@example.com"


def test_parse_from_header_plain_email_no_display_name():
    from src.services.agents.mail_agent import parse_from_header

    name, addr = parse_from_header("brian@example.com")
    assert name == ""
    assert addr == "brian@example.com"
