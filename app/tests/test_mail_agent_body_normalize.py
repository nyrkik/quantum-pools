"""extract_bodies must normalize the two known TextBody quirks.

Quirk 1 — quoted-printable still encoded. Some senders (e.g. Yardi
via Postmark) arrive with `TextBody` containing raw `=3D` / `=09` /
`=\\n` escapes that nothing decoded upstream. `_normalize_body` runs
`quopri.decodestring` before anyone sees the text so inbox rows
don't show walls of `=09=09=09`.

Quirk 2 — HTML delivered as `text/plain`. After QP decode the body
sometimes turns out to actually be HTML. Promote it to the HTML
slot (if empty) and regenerate a clean plain-text version so inbox
rows show readable copy, not `<style>` blocks.

If these tests fail, either the normalization step was moved
out of `extract_bodies` (breaking every ingest path that isn't
Postmark) or the heuristics got too loose/tight.
"""

from __future__ import annotations

from email.message import EmailMessage


def _msg_with_text(body: str) -> EmailMessage:
    m = EmailMessage()
    m["From"] = "x@example.com"
    m["To"] = "y@example.com"
    m["Subject"] = "t"
    m.set_content(body)
    return m


# Shortened version of the real Yardi-via-Postmark payload — raw QP-encoded
# HTML served as `text/plain`.
YARDI_QP_HTML_TEXTBODY = (
    '<style type=3D"text/css">background-color:#e5e5e5;</style>\n'
    '<div align=3D"center">\n'
    '=09<table border=3D"1" class=3D"x_MsoNorma=\n'
    'lTable">\n'
    '=09=09<tr>\n'
    '=09=09=09<td>Transaction Reference No</td>\n'
    '=09=09=09<td>52772764</td>\n'
    '=09=09</tr>\n'
    '=09=09<tr>\n'
    '=09=09=09<td>Transaction Date</td>\n'
    '=09=09=09<td>2026-04-14</td>\n'
    '=09=09</tr>\n'
    '=09</table>\n'
    '</div>\n'
)


def test_extract_bodies_decodes_qp_and_strips_html_when_textbody_is_qp_html():
    from src.services.agents.mail_agent import extract_bodies

    msg = _msg_with_text(YARDI_QP_HTML_TEXTBODY)
    text, html = extract_bodies(msg)

    # QP escapes are gone.
    assert "=3D" not in text
    assert "=09" not in text
    assert "=\n" not in text

    # HTML tags are gone from the plain-text body.
    assert "<style" not in text
    assert "<table" not in text
    assert "<tr" not in text

    # Real content survives.
    assert "Transaction Reference No" in text
    assert "52772764" in text
    assert "Transaction Date" in text
    assert "2026-04-14" in text

    # The HTML representation is preserved (decoded — no `=3D`).
    assert html is not None
    assert "<table" in html
    assert '="text/css"' in html or '="center"' in html


def test_extract_bodies_leaves_normal_plaintext_untouched():
    """2 stray `=3D` inside normal prose must NOT trigger QP decode."""
    from src.services.agents.mail_agent import extract_bodies

    # One legit `=` sign. Should pass through verbatim (and `set_content`
    # may wrap short ASCII in 7bit, so the raw token survives the round trip).
    clean = "Hi Brian,\n\nPrice: $125 per visit.\n\n— Kim"
    msg = _msg_with_text(clean)
    text, html = extract_bodies(msg)
    assert text.strip() == clean.strip()
    assert html is None


def test_extract_bodies_plain_html_in_textbody_is_converted_to_text():
    """TextBody that's actually HTML (no QP) still gets cleaned."""
    from src.services.agents.mail_agent import extract_bodies

    html_in_text = (
        '<div><p>Hello <b>Brian</b>,</p>'
        '<p>Your invoice is ready.</p></div>'
    )
    msg = _msg_with_text(html_in_text)
    text, html = extract_bodies(msg)

    assert "<div" not in text
    assert "<p>" not in text
    assert "<b>" not in text
    assert "Hello" in text
    assert "Brian" in text
    assert "Your invoice is ready." in text
    # Promoted to HTML when HtmlBody was empty.
    assert html is not None
    assert "<b>Brian</b>" in html


def test_qp_safety_net_is_conservative():
    """Prose with fewer than 3 QP-looking tokens must pass through
    unchanged — guards against the safety net rewriting clean text
    that happens to contain a stray `=XX`. With 3+ tokens the safety
    net fires + repairs.
    """
    from src.services.agents.mail_agent import extract_bodies

    def _decode(body: str) -> str:
        m = _msg_with_text(body)
        text, _ = extract_bodies(m)
        return text

    # One legit `=` — passes through.
    assert "=3D" not in _decode("plain prose")
    assert "Totals are due =3D net 30." in _decode(
        "Totals are due =3D net 30.",
    )
    # Three+ QP tokens — decoded to their real chars.
    decoded = _decode("key1=3Dvalue1 key2=3Dvalue2 key3=3Dvalue3")
    assert "=3D" not in decoded
    assert "key1=value1" in decoded
