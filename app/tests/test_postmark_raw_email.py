"""Postmark ingest prefers ``RawEmail`` over pre-parsed TextBody.

Provider-level body pre-parsing can mangle MIME for some senders (see
the Yardi ACH case). When Postmark sends us the raw RFC 5322 content,
we parse it with Python's email library — the same pipeline Gmail raw
ingest uses — so QP / base64 / charset / multipart quirks are handled
by the standard library rather than by trusting the provider.

If these tests fail, someone reintroduced the trust-Postmark-TextBody
path as the primary — that's the class of regression that lets Yardi-
style quirks slip through again.
"""

from __future__ import annotations

from src.services.inbound_email_service import InboundEmailService


# A realistic Postmark `RawEmail` — multipart/alternative with the
# text/html part quoted-printable-encoded, no text/plain part at all
# (the Yardi-style shape).
YARDI_STYLE_RAW_EMAIL = (
    "From: DoNotReply@Yardi.com\r\n"
    "To: support@sapphire-pools.com\r\n"
    "Subject: Remittance amount $499.00 2026-04-20\r\n"
    "MIME-Version: 1.0\r\n"
    'Content-Type: text/html; charset="utf-8"\r\n'
    "Content-Transfer-Encoding: quoted-printable\r\n"
    "\r\n"
    '<style type=3D"text/css">background-color:#e5e5e5;</style>\r\n'
    '<div align=3D"center">\r\n'
    "=09<table>\r\n"
    "=09=09<tr>\r\n"
    "=09=09=09<td>Transaction Reference No</td>\r\n"
    "=09=09=09<td>52772764</td>\r\n"
    "=09=09</tr>\r\n"
    "=09</table>\r\n"
    "</div>\r\n"
)


def test_postmark_raw_email_parses_qp_html_without_leaving_encoded_escapes():
    payload = {
        "From": "DoNotReply@Yardi.com",
        "FromFull": {"Email": "DoNotReply@Yardi.com", "Name": ""},
        "ToFull": [{"Email": "support@sapphire-pools.com"}],
        "Subject": "Remittance amount $499.00 2026-04-20",
        # TextBody still carries the garbage — proves we ignore it
        # when RawEmail is available.
        "TextBody": "=09=09=09<td>garbage</td>",
        "HtmlBody": "",
        "RawEmail": YARDI_STYLE_RAW_EMAIL,
        "Headers": [],
        "Attachments": [],
    }

    parsed = InboundEmailService()._parse_postmark(payload)

    # body_plain is the HTML-stripped, QP-decoded text.
    assert "=3D" not in parsed.body_plain
    assert "=09" not in parsed.body_plain
    assert "<table" not in parsed.body_plain
    assert "<style" not in parsed.body_plain
    assert "Transaction Reference No" in parsed.body_plain
    assert "52772764" in parsed.body_plain

    # HTML body is preserved (decoded — no `=3D`).
    assert parsed.body_html
    assert "<table" in parsed.body_html
    assert "=3D" not in parsed.body_html


def test_postmark_falls_back_to_textbody_when_rawemail_absent():
    """Servers without "Include raw email content" enabled still work —
    we fall back to TextBody/HtmlBody, and extract_bodies' normalize
    step handles the Yardi-style quirk as defense-in-depth."""
    payload = {
        "From": "sender@example.com",
        "FromFull": {"Email": "sender@example.com", "Name": ""},
        "ToFull": [{"Email": "support@sapphire-pools.com"}],
        "Subject": "test",
        "TextBody": "Plain text content.",
        "HtmlBody": "<p>Plain text content.</p>",
        # No RawEmail field.
        "Headers": [],
        "Attachments": [],
    }

    parsed = InboundEmailService()._parse_postmark(payload)
    assert parsed.body_plain == "Plain text content."
    assert parsed.body_html == "<p>Plain text content.</p>"


def test_postmark_empty_rawemail_falls_back_to_textbody():
    """Empty string is NOT treated as a valid RawEmail — we fall
    through to TextBody/HtmlBody per the ``or`` guard in the helper."""
    payload = {
        "From": "sender@example.com",
        "FromFull": {"Email": "sender@example.com", "Name": ""},
        "ToFull": [{"Email": "support@sapphire-pools.com"}],
        "Subject": "test",
        "TextBody": "fallback text",
        "HtmlBody": "",
        "RawEmail": "",
        "Headers": [],
        "Attachments": [],
    }

    parsed = InboundEmailService()._parse_postmark(payload)
    assert parsed.body_plain == "fallback text"
