"""IMAP polling, email parsing, Gmail label management.

Body decoding follows the canonical 3-stage pipeline described in
``docs/email-body-pipeline-refactor.md``:

1. **Parse** — stdlib ``email`` with ``policy=default`` gives us a tree
   of ``EmailMessage`` parts.
2. **Normalize** — ``decode_part`` handles per-part bytes → clean
   unicode (charset fallback via ``charset-normalizer`` → mojibake
   repair via ``ftfy`` → Unicode NFC → zero-width strip). Matches
   JMAP RFC 8621's best-effort-with-U+FFFD contract — never raises.
3. **Use** — ``_html_to_text`` for text/html parts (``inscriptis``,
   layout-aware), ``strip_quoted_reply`` + ``strip_email_signature``
   for downstream AI context (``mail-parser-reply``).

Per-call diagnostics accumulate in a ContextVar so the orchestrator
can emit ``email.body_normalized`` with an accurate flag set.
"""

import contextvars
import os
import re
import email
import logging
import unicodedata
from email.header import decode_header

from imapclient import IMAPClient

# Per-task flags from the last ``extract_bodies`` call. Read + cleared
# by ``consume_last_body_normalize_flags`` in the orchestrator so it can
# emit ``email.body_normalized``. ContextVar isolates flags per async
# task so concurrent ingests don't overwrite each other.
_BODY_NORMALIZE_FLAGS: contextvars.ContextVar[dict[str, bool]] = \
    contextvars.ContextVar("_body_normalize_flags", default={})


# Zero-width + BOM characters that marketers insert to pad Gmail previews.
# Stripped at the end of the normalize stage.
_ZERO_WIDTH_RE = re.compile(r"[\u200B\u200C\u200D\uFEFF]")


def _current_diag() -> dict[str, bool]:
    """Return (and lazily create) the diagnostics dict for the active
    extract_bodies call. ``decode_part`` writes flag keys into it; the
    orchestrator reads via ``consume_last_body_normalize_flags``."""
    d = _BODY_NORMALIZE_FLAGS.get()
    if not d:
        d = {}
        _BODY_NORMALIZE_FLAGS.set(d)
    return d


def decode_part(part) -> str:
    """Decode a single text part's payload to clean unicode.

    The normalize stage of the pipeline. Runs:

    1. ``part.get_payload(decode=True)`` — stdlib unwraps
       Content-Transfer-Encoding (base64 / QP / 7bit / 8bit).
    2. Bytes → unicode: try the declared charset first; on failure
       (``LookupError`` for unknown encoding name, ``UnicodeDecodeError``
       for wrong encoding) fall back to ``charset-normalizer``'s best
       guess, then ``latin-1`` with replacement (always succeeds).
    3. ``ftfy.fix_text`` — fix mojibake (UTF-8-bytes-mis-decoded-as-
       Latin-1 etc). ``uncurl_quotes=False`` to preserve legit curly
       quotes in HTML email.
    4. ``unicodedata.normalize("NFC", …)`` — canonical Unicode form.
    5. Strip zero-width + BOM characters.

    Never raises. Diagnostic flags for what fired land in the current
    extract_bodies call's ContextVar so the orchestrator can emit
    ``email.body_normalized``.
    """
    diag = _current_diag()

    try:
        payload = part.get_payload(decode=True)
    except Exception:  # noqa: BLE001
        payload = None
    if payload is None:
        raw = part.get_payload()
        if isinstance(raw, str):
            return _post_decode_normalize(raw, diag)
        return ""

    if isinstance(payload, str):
        return _post_decode_normalize(payload, diag)

    text = _bytes_to_unicode(payload, part.get_content_charset(), diag)
    return _post_decode_normalize(text, diag)


def _bytes_to_unicode(
    payload: bytes, declared_charset: str | None, diag: dict[str, bool],
) -> str:
    """Bytes → unicode with multi-stage fallback. Order matches the
    canonical pipeline — try what the sender declared first, because
    they're right more often than heuristics; fall back to detection
    only when the declaration fails or is missing."""
    declared = (declared_charset or "").strip().lower() or None
    if declared:
        try:
            return payload.decode(declared)
        except (LookupError, UnicodeDecodeError):
            diag["charset_fallback_used"] = True

    try:
        from charset_normalizer import from_bytes
        best = from_bytes(payload).best()
        if best is not None:
            diag.setdefault("charset_fallback_used", True)
            return str(best)
    except Exception as e:  # noqa: BLE001
        logger.debug("charset-normalizer failed: %s", e)

    diag["charset_fallback_used"] = True
    return payload.decode("latin-1", errors="replace")


def _post_decode_normalize(text: str, diag: dict[str, bool]) -> str:
    """ftfy + NFC + zero-width strip + QP safety net. Runs on every
    unicode body, regardless of how it was decoded — cleans up both
    our own fallback decodes AND content that arrived pre-mangled
    from upstream (Postmark's TextBody for senders who mis-declare
    Content-Transfer-Encoding).

    The QP safety net is the only "already-decoded" repair — every
    other upstream quirk (charset lies, mojibake, zero-widths) is
    handled by the primary decode + ftfy + NFC path. Once Postmark
    RawEmail is enabled, the safety net effectively never fires.
    """
    if not text:
        return text

    # QP safety net — if 3+ QP tokens remain in the "decoded" text,
    # upstream didn't actually decode the CTE. Re-decode with quopri.
    if len(_QP_SAFETY_NET_RE.findall(text)) >= 3:
        try:
            import quopri
            decoded = quopri.decodestring(
                text.encode("utf-8", errors="replace"),
            ).decode("utf-8", errors="replace")
            if decoded != text:
                text = decoded
                diag["qp_decoded"] = True
        except Exception as e:  # noqa: BLE001
            logger.debug("QP safety net failed: %s", e)

    try:
        import ftfy
        before = text
        text = ftfy.fix_text(text, uncurl_quotes=False)
        if text != before:
            diag["mojibake_repaired"] = True
    except Exception as e:  # noqa: BLE001
        logger.debug("ftfy failed: %s", e)

    text = unicodedata.normalize("NFC", text)

    before = text
    text = _ZERO_WIDTH_RE.sub("", text)
    if text != before:
        diag["zero_width_stripped"] = True

    return text


# Safety-net QP detection — matches the classic hex escape or soft
# line break. Kept minimal (the old normalize had a broader set of
# helpers; most of that logic is now structural in decode_part).
_QP_SAFETY_NET_RE = re.compile(r"=[0-9A-Fa-f]{2}|=\r?\n")

# HTML-in-plaintext detection — after canonical decode, if the body
# still contains an HTML structural tag in the first 500 chars, the
# sender labeled HTML content as text/plain (common when Postmark's
# TextBody wraps HTML-only mail).
_HTML_TAG_RE = re.compile(
    r"<(?:html|body|head|style|div|table|tbody|tr|td|p|span|img|a|h[1-6]|ul|ol|br|meta|link)\b",
    re.IGNORECASE,
)


def _looks_like_html(text: str) -> bool:
    """True when the first 500 chars contain an HTML structural tag."""
    if not text:
        return False
    return bool(_HTML_TAG_RE.search(text[:500]))

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


def parse_from_header(raw: str) -> tuple[str, str]:
    """Return ``(display_name, email_addr)`` from a raw RFC 5322 From header.

    Prefers ``email.headerregistry.Address`` (RFC 5322-compliant grammar)
    over the legacy ``email.utils.parseaddr`` regex, with graceful
    fallbacks. ``display_name`` is empty when the header had no
    ``"Name" <addr>`` form; callers then fall back to a domain-based
    prettification for VERP-style opaque locals.
    """
    if not raw:
        return ("", "")
    decoded = decode_email_header(raw).strip()
    # Structured parse — let the email lib's header grammar do the work.
    try:
        from email import message_from_string, policy
        parsed_msg = message_from_string(
            f"From: {decoded}\n\n", policy=policy.default,
        )
        header = parsed_msg["From"]
        if header is not None and getattr(header, "addresses", None):
            a = header.addresses[0]
            return (a.display_name or "", a.addr_spec or "")
    except Exception as e:  # noqa: BLE001
        logger.debug("parse_from_header structured parse failed: %s", e)
    # Hard fallback: extract ``<addr>`` by regex.
    m = re.search(r"<([^>]+)>", decoded)
    if m:
        name = decoded[: m.start()].strip().strip('"').strip()
        return (name, m.group(1).strip())
    if "@" in decoded:
        return ("", decoded)
    return (decoded, "")


def _mailparser_reply_latest(text: str) -> str | None:
    """Return the most-recent (top) reply body from a thread, or None
    when ``mail-parser-reply`` can't meaningfully split the text.

    Used by ``strip_quoted_reply`` + ``strip_email_signature`` — both
    operate on "the user's latest reply only" which is exactly what
    the library's ``replies[0]`` yields.
    """
    if not text:
        return None
    try:
        from mailparser_reply import EmailReplyParser
        parsed = EmailReplyParser(languages=["en"]).read(text)
        if parsed.replies:
            body = parsed.replies[0].body
            if body is not None:
                return body
    except Exception as e:  # noqa: BLE001
        logger.debug("mail-parser-reply failed: %s", e)
    return None


def strip_quoted_reply(text: str) -> str:
    """Drop the quoted reply chain, keeping only the most-recent message.

    Thin wrapper around ``mail-parser-reply`` — handles ``On … wrote:``,
    ``From: … Subject:``, forwarded-message markers, ``>``-quotes,
    mobile sign-offs, all with multi-language support. Falls back to
    the input text when the library can't split (single-turn messages
    look the same before and after — that's expected)."""
    if not text:
        return text
    latest = _mailparser_reply_latest(text)
    if latest is not None:
        return latest.strip()

    return text


def strip_email_signature(text: str) -> str:
    """Drop the trailing signature + disclaimer block.

    Thin wrapper around ``mail-parser-reply`` — the library's
    reply-parse already identifies signatures / sign-offs /
    disclaimers per message. Falls back to the input when the library
    can't identify one (short transactional emails often have no
    detectable signature — returning the input as-is is correct)."""
    if not text:
        return text
    try:
        from mailparser_reply import EmailReplyParser
        parsed = EmailReplyParser(languages=["en"]).read(text)
        if parsed.replies:
            # mail-parser-reply's `body` is signature-stripped already.
            return parsed.replies[0].body.strip()
    except Exception as e:  # noqa: BLE001
        logger.debug("mail-parser-reply signature strip failed: %s", e)
    return text


def _clean_html(html: str) -> str:
    """Convert HTML to clean plain text via ``inscriptis``.

    Inscriptis is layout-aware (CSS display rules, table cell spacing,
    list bullets) and wins the HTML→text benchmarks cited in the
    refactor plan. Collapses excessive blank lines afterwards so the
    inbox preview doesn't have big vertical gaps."""
    if not html:
        return html
    try:
        import inscriptis
        text = inscriptis.get_text(html)
    except Exception as e:  # noqa: BLE001
        logger.warning("inscriptis failed, returning empty text: %s", e)
        return ""
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


def extract_text_body(msg) -> str:
    """Extract plain text body from email message."""
    raw, _ = extract_bodies(msg)
    return raw


def extract_bodies(msg) -> tuple[str, str | None]:
    """Extract (text_body, html_body) via the canonical pipeline.

    Walks every part; delegates per-part decoding to ``decode_part``.
    For multipart messages, picks the first text/plain part and the
    first text/html part. Falls back to generating plain text from
    HTML via ``_clean_html`` (inscriptis) when only HTML is present.
    Finally runs ``_unwrap_embedded_mime`` on the text body in case a
    provider handed us a full MIME envelope stringified as text.

    Diagnostic flags (``mime_unwrapped``, ``mojibake_repaired``,
    ``charset_fallback_used``, ``zero_width_stripped``,
    ``html_stripped_from_text``) land in the ContextVar for the
    orchestrator to pick up via ``consume_last_body_normalize_flags``.
    """
    # Reset diagnostics for this call — every extract_bodies starts clean.
    _BODY_NORMALIZE_FLAGS.set({})

    text_raw = ""
    html_raw: str | None = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and not text_raw:
                text_raw = decode_part(part)
            elif content_type == "text/html" and html_raw is None:
                html_raw = decode_part(part)
        if not text_raw and html_raw:
            text_raw = _clean_html(html_raw)
            if text_raw:
                _current_diag()["html_stripped_from_text"] = True
    else:
        decoded = decode_part(msg)
        if msg.get_content_type() == "text/html":
            html_raw = decoded
            text_raw = _clean_html(decoded)
            if text_raw:
                _current_diag()["html_stripped_from_text"] = True
        else:
            text_raw = decoded

    if text_raw:
        before_unwrap = text_raw
        text_raw = _unwrap_embedded_mime(text_raw)
        if text_raw != before_unwrap:
            _current_diag()["mime_unwrapped"] = True

    # HTML-in-plaintext — after canonical decode + unwrap, if the
    # "plain text" body still looks like HTML, promote it to html_raw
    # (when empty) and regenerate clean plain text. This catches the
    # case where a sender handed Postmark HTML-only mail with no
    # TextBody, so Postmark stuffed HTML into TextBody and sent
    # HtmlBody empty.
    if text_raw and _looks_like_html(text_raw):
        if not html_raw:
            html_raw = text_raw
        text_raw = _clean_html(text_raw)
        _current_diag()["html_stripped_from_text"] = True

    return text_raw, html_raw


def renormalize_stored_body(
    body: str, body_html: str | None,
) -> tuple[str, str | None, dict[str, bool]]:
    """Re-run the canonical normalize + HTML-detect stages on already-
    stored body text. Used by the backfill script to repair messages
    ingested before the current pipeline shipped.

    Does NOT repeat the part-walking / CTE-decoding logic of
    ``extract_bodies`` — the body is already unicode-decoded at this
    point. Runs: QP safety net → ftfy → NFC → zero-width strip →
    HTML-in-plaintext detect. Returns ``(body, body_html, diag)``.
    """
    _BODY_NORMALIZE_FLAGS.set({})
    diag = _current_diag()
    new_body = _post_decode_normalize(body or "", diag)
    new_html = body_html
    if new_body and _looks_like_html(new_body):
        if not new_html:
            new_html = new_body
        new_body = _clean_html(new_body)
        diag["html_stripped_from_text"] = True
    return new_body, new_html, dict(diag)


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
