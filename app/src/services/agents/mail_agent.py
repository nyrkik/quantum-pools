"""IMAP polling, email parsing, Gmail label management."""

import os
import re
import email
import logging
from email.header import decode_header

from imapclient import IMAPClient

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
    match = re.search(r'\nOn .{10,80} wrote:\s*\n', text)
    if match:
        return text[:match.start()].strip()

    # Pattern 2: "From: ... To: ... Date: ... Subject:" block (Outlook)
    match = re.search(r'\nFrom:\s*.+\nTo:\s*.+\n(?:Date|Sent):\s*.+\nSubject:', text)
    if match:
        return text[:match.start()].strip()

    # Pattern 3: "---------- Forwarded message" or "-------- Original Message"
    match = re.search(r'\n-{3,}\s*(Forwarded|Original)\s', text)
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


def _clean_html(html: str) -> str:
    """Convert HTML to clean plain text."""
    from html import unescape
    # Replace block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
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


def extract_text_body(msg) -> str:
    """Extract plain text body from email message, stripping quoted reply chains."""
    raw = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    raw = payload.decode(charset, errors="replace")
                    break
        if not raw:
            # Fallback to HTML if no plain text
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        raw = _clean_html(payload.decode(charset, errors="replace"))
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            raw = _clean_html(text) if msg.get_content_type() == "text/html" else text

    return strip_quoted_reply(raw) if raw else ""
