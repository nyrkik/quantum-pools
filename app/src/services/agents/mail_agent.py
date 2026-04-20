"""IMAP polling, email parsing, Gmail label management."""

import contextvars
import os
import re
import email
import logging
import quopri
from email.header import decode_header

from imapclient import IMAPClient

# Per-task flags from the last ``extract_bodies`` call. Read + cleared
# by ``consume_last_body_normalize_flags`` in the orchestrator so it can
# emit ``email.body_normalized`` with payload `{mime_unwrapped,
# qp_decoded, html_stripped_from_text}`. ContextVar isolates flags per
# async task so concurrent ingests don't overwrite each other.
_BODY_NORMALIZE_FLAGS: contextvars.ContextVar[dict[str, bool]] = \
    contextvars.ContextVar("_body_normalize_flags", default={})

logger = logging.getLogger(__name__)

# Config from env
GMAIL_USER = os.environ.get("AGENT_GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("AGENT_GMAIL_PASSWORD", "")
IMAP_HOST = os.environ.get("AGENT_IMAP_HOST", "imap.gmail.com")

QP_LABEL = "QP-Processed"
_label_ensured = False


def _ensure_label(client: IMAPClient):
    """Create the QP-Processed label if it doesn't exist."""
    global _label_ensured
    if _label_ensured:
        return
    try:
        folders = [f[2] for f in client.list_folders()]
        if QP_LABEL not in folders:
            client.create_folder(QP_LABEL)
            logger.info(f"Created Gmail label: {QP_LABEL}")
        _label_ensured = True
    except Exception as e:
        logger.error(f"Failed to ensure label: {e}")
        _label_ensured = True  # Don't retry every cycle


def poll_inbox():
    """Connect to Gmail IMAP and fetch emails not yet processed by QP.
    Uses a Gmail label instead of UNSEEN to avoid missing emails opened elsewhere."""
    messages = []
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)

        _ensure_label(client)

        client.select_folder("INBOX")

        # Search for emails NOT labeled QP-Processed
        # Gmail IMAP uses X-GM-LABELS for label queries
        uids = client.gmail_search(f"-label:{QP_LABEL} newer_than:2d")
        if not uids:
            client.logout()
            return []

        # Fetch only the newest 10 to avoid overload
        uids = uids[-10:]
        raw_messages = client.fetch(uids, ["RFC822"])

        for uid, data in raw_messages.items():
            raw = data[b"RFC822"]
            msg = email.message_from_bytes(raw)
            messages.append((str(uid), msg))

        client.logout()
    except Exception as e:
        logger.error(f"IMAP error: {e}")

    return messages


def fetch_sent_emails() -> list[tuple[str, email.message.Message]]:
    """Fetch recent sent emails that haven't been tracked yet.

    Checks [Gmail]/Sent Mail for outbound messages from org addresses.
    These are replies sent via Gmail/alias, not through the app.
    """
    messages = []
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)
        _ensure_label(client)

        client.select_folder("[Gmail]/Sent Mail")
        uids = client.gmail_search(f"-label:{QP_LABEL} newer_than:2d")
        if not uids:
            client.logout()
            return []

        uids = uids[-10:]
        raw_messages = client.fetch(uids, ["RFC822"])

        for uid, data in raw_messages.items():
            raw = data[b"RFC822"]
            msg = email.message_from_bytes(raw)
            messages.append((str(uid), msg))

        client.logout()
    except Exception as e:
        logger.error(f"IMAP sent folder error: {e}")

    return messages


def mark_sent_processed(uid: str):
    """Add the QP-Processed label to a sent message."""
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)
        client.select_folder("[Gmail]/Sent Mail")
        client.add_gmail_labels([int(uid)], [QP_LABEL])
        client.logout()
    except Exception as e:
        logger.error(f"Failed to label sent message {uid}: {e}")


def mark_processed(uid: str):
    """Add the QP-Processed label to a message after processing."""
    try:
        client = IMAPClient(IMAP_HOST, ssl=True)
        client.login(GMAIL_USER, GMAIL_PASSWORD)
        client.select_folder("INBOX")

        # Add the label using Gmail's IMAP extension
        client.add_gmail_labels([int(uid)], [QP_LABEL])

        client.logout()
    except Exception as e:
        logger.error(f"Failed to mark processed {uid}: {e}")


def decode_email_header(header):
    """Decode email header handling various encodings."""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def strip_quoted_reply(text: str) -> str:
    """Remove quoted reply chains from email body, keeping only the new content."""
    if not text:
        return text

    # Pattern 1: "On <date>, <person> wrote:" (Apple Mail, Gmail)
    match = re.search(r'On .{10,80} wrote:\s', text)
    if match:
        return text[:match.start()].strip()

    # Pattern 2: "Sent from my iPhone/iPad" then quoted content
    match = re.search(r'Sent from my (iPhone|iPad|Galaxy|device)', text)
    if match:
        return text[:match.start()].strip()

    # Pattern 3: "From: ... To: ... Date: ... Subject:" block (Outlook)
    match = re.search(r'From:\s*.+\nTo:\s*.+\n(?:Date|Sent):\s*.+\nSubject:', text)
    if match:
        return text[:match.start()].strip()

    # Pattern 4: "---------- Forwarded message" or "-------- Original Message"
    match = re.search(r'-{3,}\s*(Forwarded|Original)\s', text)
    if match:
        return text[:match.start()].strip()

    # Pattern 4: Line starting with ">" (traditional quoting)
    lines = text.split('\n')
    new_lines = []
    hit_quote = False
    for line in lines:
        if line.strip().startswith('>'):
            hit_quote = True
            continue
        if hit_quote and not line.strip():
            continue  # Skip blank lines after quotes
        if hit_quote:
            break  # Stop at first non-quote, non-blank after quotes
        new_lines.append(line)

    if hit_quote and new_lines:
        return '\n'.join(new_lines).strip()

    return text


def strip_email_signature(text: str) -> str:
    """Remove everything after the signature/sign-off. Keep only the message body."""
    if not text:
        return text

    # Find the earliest cut point from any of these patterns
    cut_at = len(text)

    # Standard sig separator "-- "
    match = re.search(r'\n-- ?\n', text)
    if match and match.start() < cut_at:
        cut_at = match.start()

    # Sign-off line — must be on its own line (possibly followed by comma and name, but not a sentence)
    # Requires: start of line, sign-off word, then comma/newline/end — NOT followed by lowercase continuation
    signoffs = r'\n(?:Best|Thanks|Thank you|Regards|Kind regards|Sincerely|Cheers|Warm regards|All the best|Respectfully|Take care|Sent from my),?\s*\n'
    match = re.search(signoffs, text, re.IGNORECASE)
    if match and match.start() < cut_at:
        cut_at = match.end()  # keep the sign-off line

    # Noise blocks — disclaimers, confidentiality, legal footers
    noise = r'(?:CONFIDENTIAL|DISCLAIMER|NOTICE\s*:|PRIVILEGED|This (?:e-?mail|message|communication) (?:is |contains |and ))'
    match = re.search(noise, text, re.IGNORECASE)
    if match:
        # Cut at the start of the line containing the noise
        line_start = text.rfind('\n', 0, match.start())
        pos = line_start if line_start >= 0 else match.start()
        if pos < cut_at:
            cut_at = pos

    if cut_at < len(text):
        return text[:cut_at].strip()

    return text


def _clean_html(html: str) -> str:
    """Convert HTML to clean plain text."""
    from html import unescape
    # Remove style blocks (CSS) and script blocks entirely
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Remove head block
    text = re.sub(r"<head[^>]*>.*?</head>", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Replace block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|tr|li|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (&nbsp; &amp; etc)
    text = unescape(text)
    # Collapse whitespace within lines but preserve line breaks
    lines = text.split("\n")
    lines = [" ".join(line.split()) for line in lines]
    # Remove excessive blank lines
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _unwrap_embedded_mime(text: str) -> str:
    """Extract inner text when a body is itself a raw MIME multipart envelope.

    Some Outlook/Exchange senders relayed via Postmark arrive with a TextBody
    that literally contains a multipart MIME structure (--boundary lines,
    Content-Type / Content-Transfer-Encoding headers) instead of decoded plain
    text. Re-parse it as a real MIME message and pull the text/plain part out.
    Returns the original text if it doesn't look like an embedded envelope.
    """
    if not text:
        return text

    stripped = text.lstrip()
    first_line = stripped.split("\n", 1)[0].rstrip("\r")

    # Must look like an opening boundary (not a closing --boundary--)
    if (
        not first_line.startswith("--")
        or first_line.endswith("--")
        or len(first_line) < 4
    ):
        return text

    boundary = first_line[2:]
    # RFC 2046 boundary character set — bail if it doesn't look right
    if not re.match(r"^[A-Za-z0-9'()+_,\-./:=?]+$", boundary):
        return text

    # Confirm a Content-Type header appears in the head of the body
    head = "\n".join(stripped.split("\n")[:20])
    if "Content-Type:" not in head:
        return text

    wrapper = (
        f'Content-Type: multipart/mixed; boundary="{boundary}"\n'
        "MIME-Version: 1.0\n\n" + stripped
    )

    try:
        from email import message_from_string, policy

        parsed = message_from_string(wrapper, policy=policy.default)
        if not parsed.is_multipart():
            return text

        def _decode_part(part) -> str:
            try:
                content = part.get_content()
                if isinstance(content, str):
                    return content
            except Exception:
                pass
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
            return payload or ""

        # Prefer text/plain
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                payload = _decode_part(part)
                if payload and payload.strip():
                    return payload.strip()

        # Fallback: text/html
        for part in parsed.walk():
            if part.get_content_type() == "text/html":
                payload = _decode_part(part)
                if payload and payload.strip():
                    return _clean_html(payload)
    except Exception as e:
        logger.warning(f"_unwrap_embedded_mime failed: {e}")

    return text


# Quoted-printable soft line breaks (`=\n`) and hex escapes (`=3D`, `=09`, …).
# Normal plain text almost never contains more than a couple of these; three
# or more inside a single body is a strong signal the content wasn't decoded
# upstream (see the Yardi-via-Postmark case).
_QP_TOKEN_RE = re.compile(r"=[0-9A-Fa-f]{2}|=\r?\n")

# Opening tags that prove a body the provider labeled `text/plain` is
# actually HTML — broad enough to catch marketing emails, tight enough to
# avoid false positives on code snippets that mention `<html` in prose.
_HTML_TAG_RE = re.compile(
    r"<(?:html|body|head|style|div|table|tbody|tr|td|p|span|img|a|h[1-6]|ul|ol|br|meta|link)\b",
    re.IGNORECASE,
)


def _looks_quoted_printable(text: str) -> bool:
    """True when the body carries ≥3 QP tokens — a soft line break or a
    `=XX` hex escape. Mirrors the `_unwrap_embedded_mime` heuristic style:
    err on the side of not rewriting clean text."""
    if not text:
        return False
    return len(_QP_TOKEN_RE.findall(text)) >= 3


def _decode_quoted_printable(text: str) -> str:
    try:
        decoded = quopri.decodestring(text.encode("utf-8", errors="replace"))
        return decoded.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.warning("_decode_quoted_printable failed: %s", e)
        return text


def _looks_like_html(text: str) -> bool:
    """True when the first 500 chars contain an HTML structural tag."""
    if not text:
        return False
    return bool(_HTML_TAG_RE.search(text[:500]))


def _normalize_body(
    text_raw: str, html_raw: str | None,
) -> tuple[str, str | None, dict[str, bool]]:
    """Clean up TextBody quirks that slip past the MIME decoder.

    Two quirks in the wild (verified against real Sapphire inbox
    messages):

    1. **Quoted-printable still encoded.** Some senders relayed via
       Postmark arrive with `TextBody` that contains raw QP escapes
       (`=3D`, `=09`, soft `=\\n` line breaks) — Postmark didn't
       decode them because the upstream Content-Transfer-Encoding
       header was missing or mis-declared. Decode with `quopri`
       before anything else touches the text.

    2. **HTML in TextBody, nothing in HtmlBody.** Once the QP is
       decoded we sometimes see the result is actually an HTML
       document. Treat that as HTML: promote to `html_raw` if we
       didn't get one, and regenerate the plain-text body via
       `_clean_html` so the inbox row isn't a wall of tags.

    Runs regardless of ingest provider — living in `extract_bodies`
    means every ingest path benefits without per-provider patching.

    Returns ``(text, html, diagnostics)`` where ``diagnostics`` names
    each transform that actually fired (for telemetry — the orchestrator
    emits `email.body_normalized` so new quirks show up in
    platform_events before users report them).
    """
    diagnostics = {"qp_decoded": False, "html_stripped_from_text": False}
    if text_raw and _looks_quoted_printable(text_raw):
        text_raw = _decode_quoted_printable(text_raw)
        diagnostics["qp_decoded"] = True
    if text_raw and _looks_like_html(text_raw):
        if not html_raw:
            html_raw = text_raw
        text_raw = _clean_html(text_raw)
        diagnostics["html_stripped_from_text"] = True
    return text_raw, html_raw, diagnostics


def extract_text_body(msg) -> str:
    """Extract plain text body from email message, stripping quoted reply chains."""
    raw, _ = extract_bodies(msg)
    return raw


def extract_bodies(msg) -> tuple[str, str | None]:
    """Extract both plain text AND original HTML body.

    Returns (text_body, html_body). text_body is always populated (converted
    from HTML if only HTML was available). html_body is the raw HTML if present,
    None otherwise.

    Safety net: if the extracted text_body still looks like a raw MIME
    multipart envelope (the Outlook/Exchange quirk some webhook providers
    surface in TextBody fields), unwrap it. This runs regardless of the
    ingest source (Postmark, Gmail, future MS Graph, etc.) so we don't
    need to remember which providers have the quirk.
    """
    text_raw = ""
    html_raw = None
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and not text_raw:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_raw = payload.decode(charset, errors="replace")
            elif content_type == "text/html" and html_raw is None:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_raw = payload.decode(charset, errors="replace")
        if not text_raw and html_raw:
            text_raw = _clean_html(html_raw)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_raw = text
                text_raw = _clean_html(text)
            else:
                text_raw = text

    if text_raw:
        before_unwrap = text_raw
        text_raw = _unwrap_embedded_mime(text_raw)
        _BODY_NORMALIZE_FLAGS.set({
            "mime_unwrapped": text_raw != before_unwrap,
        })
    else:
        _BODY_NORMALIZE_FLAGS.set({"mime_unwrapped": False})

    text_raw, html_raw, norm_flags = _normalize_body(text_raw, html_raw)
    prior = _BODY_NORMALIZE_FLAGS.get()
    _BODY_NORMALIZE_FLAGS.set({**prior, **norm_flags})

    return text_raw, html_raw


def consume_last_body_normalize_flags() -> dict[str, bool]:
    """Return and clear the diagnostic flags from the most recent
    ``extract_bodies`` call in this context. Designed for the
    orchestrator to read right after it calls ``extract_bodies`` so it
    can emit ``email.body_normalized`` with an accurate payload. Uses
    a ContextVar so concurrent ingests don't stomp each other's flags.
    """
    flags = _BODY_NORMALIZE_FLAGS.get()
    _BODY_NORMALIZE_FLAGS.set({})
    return flags
