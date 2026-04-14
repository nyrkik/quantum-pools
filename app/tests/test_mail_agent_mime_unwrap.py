"""extract_bodies must unwrap raw-MIME-in-text-field regardless of ingest path.

The Outlook/Exchange quirk where Postmark's TextBody contains the raw
multipart envelope (boundary + Content-Type headers + body) is handled
centrally in extract_bodies, so every provider (Postmark, SendGrid,
Mailgun, Generic, Gmail raw, future MS Graph) gets the fix without
provider-specific patching. If this test fails, someone has re-scoped
the unwrap to a single parser and the quirk will leak for other sources.
"""

from __future__ import annotations

from email.message import EmailMessage


OUTLOOK_RAW_MIME_BODY = """--_000_BYAPR10MB271007549B5A142E1A9A0730E3242BYAPR10MB2710namp_
Content-Type: text/plain; charset="us-ascii"
Content-Transfer-Encoding: quoted-printable

I do not but I ask our regional office.

ASHLEY OVERTON
Community Manager | Coventry Park Apartments

--_000_BYAPR10MB271007549B5A142E1A9A0730E3242BYAPR10MB2710namp_
Content-Type: text/html; charset="us-ascii"
Content-Transfer-Encoding: quoted-printable

<p>I do not but I ask our regional office.</p>

--_000_BYAPR10MB271007549B5A142E1A9A0730E3242BYAPR10MB2710namp_--
"""


def _msg_with_text(body: str) -> EmailMessage:
    """Minimal EmailMessage whose single text/plain part carries ``body``."""
    m = EmailMessage()
    m["From"] = "x@example.com"
    m["To"] = "y@example.com"
    m["Subject"] = "t"
    m.set_content(body)
    return m


def test_extract_bodies_unwraps_raw_mime_in_text_part():
    from src.services.agents.mail_agent import extract_bodies

    msg = _msg_with_text(OUTLOOK_RAW_MIME_BODY)
    text, _ = extract_bodies(msg)

    # Boundary and part headers must be gone
    assert "--_000_BYAPR10MB" not in text
    assert "Content-Transfer-Encoding" not in text
    # Real body content must be present
    assert "I do not but I ask our regional office." in text


def test_extract_bodies_leaves_clean_text_alone():
    """Idempotent — a normal plaintext body must pass through unchanged."""
    from src.services.agents.mail_agent import extract_bodies

    clean = "Hi Brian,\n\nThanks for the quote. We'll schedule next week.\n\n— Kim"
    msg = _msg_with_text(clean)
    text, _ = extract_bodies(msg)
    assert text.strip() == clean.strip()


def test_extract_bodies_leaves_html_alone_when_no_quirk():
    """HTML-only message still converts via _clean_html without triggering unwrap."""
    from src.services.agents.mail_agent import extract_bodies

    m = EmailMessage()
    m["From"] = "x@example.com"
    m["To"] = "y@example.com"
    m["Subject"] = "t"
    m.set_content("<p>Hello <b>world</b></p>", subtype="html")
    text, html = extract_bodies(m)
    assert "Hello" in text
    assert html and "<b>world</b>" in html
